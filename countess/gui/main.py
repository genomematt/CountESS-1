import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import sys
from dataclasses import dataclass
import random

import pandas as pd
import dask.dataframe as dd
import numpy as np

from countess import VERSION
from countess.core.plugins import get_plugin_classes
from countess.gui.config import PluginConfigurator, DataFramePreview
from countess.plugins.pivot import DaskPivotPlugin
from countess.core.dataflow import PipelineGraph, PipelineNode
from countess.core.config import read_config, write_config, export_config_graphviz

def _limit(value, min_value, max_value):
    return max(min_value, min(max_value, value))

def _snap(value, scale, steps=21):
    step_size = scale / steps
    value = _limit(value, 0, scale)
    return ((value // step_size) + 0.5) * step_size

def _geometry(widget):
    return (
        widget.winfo_x(),
        widget.winfo_y(),
        widget.winfo_width(),
        widget.winfo_height()
    )

class DraggableMixin:

    __mousedown = False
    __moving = False
    __ghost = None
    __ghost_line = None

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bind("<Button-1>", self.__on_start, add="+")
        self.bind("<B1-Motion>", self.__on_motion, add="+")
        self.bind("<ButtonRelease-1>", self.__on_release, add="+")

    def __on_start(self, event):
        self['cursor'] = 'fleur'
        self.__start_x = event.x
        self.__start_y = event.y
        self.after(500, self.__on_timeout)
        self.__mousedown = True

    def __on_timeout(self):
        if self.__mousedown and not self.__moving:
            self['cursor'] = 'plus'
            self.__ghost = tk.Frame(self.master)
            self.__ghost.place(self.place_info())
            self.__ghost_line = ConnectingLine(self.master, self, self.__ghost, 'red', True)

    def __on_motion(self, event):
        self.__moving = True
        mw = self.master.winfo_width()
        mh = self.master.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = _snap(self.winfo_x() - self.__start_x + event.x, mw)
        y = _snap(self.winfo_y() - self.__start_y + event.y, mh)

        if self.__ghost:
            self.__ghost.place({'relx': x / mw, 'rely': y / mh})
        elif self.place_info()['relx']:
            self.place({'relx': x / mw, 'rely': y / mh})
        else:
            self.place({'x': x, 'y': y})

    def __on_release(self, event):
        if self.__ghost is not None:
            self.event_generate("<<GhostRelease>>", x=event.x, y=event.y)
            self.__ghost_line.destroy()
            self.__ghost.destroy()
            self.__ghost = None
        self.__mousedown = False
        self.__moving = False
        self['cursor'] = 'hand1'


class FixedUnbindMixin:

    def unbind(self, seq, funcid):
        # widget.unbind(seq, funcid) doesn't actually work as documented. This is
        # my own take on the horrible hacks found at https://bugs.python.org/issue31485
        # and https://mail.python.org/pipermail/tkinter-discuss/2012-May/003152.html
        # Also quite horrible.  "I'm not proud, but I'm not tired either"

        self.bind(seq, re.sub(
            r'^if {"\[' + funcid + '.*$', '', self.bind(seq), flags=re.M
        ))
        self.deletecommand(funcid)


class ConnectingLine:
    line = None
    def __init__(self, canvas, widget1, widget2, color='black', switch=False):
        self.canvas = canvas
        self.widget1 = widget1
        self.widget2 = widget2
        self.color = color
        self.switch = switch

        # XXX I'm not totally in love with all this event
        # binding and unbinding and might replace it with
        # a GraphWrapper-level binding.

        self.widget1_bind = self.widget1.bind("<Configure>", self.update_line, add=True)
        self.widget2_bind = self.widget2.bind("<Configure>", self.update_line, add=True)
        self.canvas_bind = self.canvas.bind("<Configure>", self.update_line, add=True)
        self.update_line()

    def update_line(self, event=None):
        x1, y1, w1, h1 = _geometry(self.widget1)
        x2, y2, w2, h2 = _geometry(self.widget2)

        xc, yc, wc, hc = _geometry(self.canvas)
        if wc > hc: 
            if self.switch and x1 > x2:
                x1, y1, w1, h1, x2, y2, w2, h2 = x2, y2, w2, h2, x1, y1, w1, h1
            coords = (
                x1 + w1 // 2, y1 + h1 // 2,
                #x1 + w1, y1 + h1 //2,
                #x1 + w1 + 20, y1 + h1//2,
                x2 - 50, y2 + h2//2,
                x2, y2 + h2//2
            )
        else:
            if self.switch and y1 > y2:
                x1, y1, w1, h1, x2, y2, w2, h2 = x2, y2, w2, h2, x1, y1, w1, h1
            coords = (
                x1 + w1 // 2, y1 + h1 // 2,
                #x1 + w1 // 2, y1 + h1,
                #x1 + w1 // 2, y1 + h1 + 20,
                x2 + w2 // 2, y2 - 50,
                x2 + w2 // 2, y2
            )

        if self.line: self.canvas.coords(self.line, *coords)
        else: self.line = self.canvas.create_line(*coords, smooth=True, width=3, arrow='last', arrowshape=(15,15,6), fill=self.color)

    def destroy(self):
        self.canvas.delete(self.line)
        self.canvas.unbind("<Configure>", self.canvas_bind)
        self.widget1.unbind("<Configure>", self.widget1_bind)
        self.widget2.unbind("<Configure>", self.widget2_bind)


plugin_classes = get_plugin_classes()

class PluginChooserFrame(tk.Frame):

    def __init__(self, master, title, callback, *a, **k):
        super().__init__(master, *a, **k)

        self.columnconfigure(0, weight=1)

        font = ('Helvetica', 16, 'bold')
        tk.Label(self, text=title, font=font).grid(row=0, column=0, sticky=tk.EW)
        label_frame = tk.LabelFrame(self, text="Choose Plugin", padx=10, pady=10)
        label_frame.grid(row=1, column=0, sticky=tk.EW)

        for n, plugin_class in enumerate(plugin_classes):
            ttk.Button(label_frame, text=plugin_class.name, command=lambda plugin_class=plugin_class: callback(plugin_class)).grid(row=n+1, column=0, sticky=tk.EW)
            ttk.Label(label_frame, text=plugin_class.title).grid(row=n+1, column=1, sticky=tk.W)


class FlippyCanvas(FixedUnbindMixin, tk.Canvas):
    """A canvas which flips all its children's X and Y
    coordinates when it goes from portrait to landscape.
    Place children with .place(relx=, rely=) for best results."""

    __flipped = False

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bind("<Configure>", self.__on_configure)

    def __flip(self, width, height):
        for c in self.winfo_children():
            c.place({
                'x': c.place_info()['y'],
                'y': c.place_info()['x'],
                'relx': c.place_info()['rely'],
                'rely': c.place_info()['relx'],
            })
        # XXX should flip canvas items as well,
        # but I didn't actually need that so I didn't bother.

    def __on_configure(self, event):
        flipped = event.height > event.width
        if flipped != self.__flipped:
            self.__flip(event.width, event.height)
            self.__flipped = flipped


class DraggableMessage(DraggableMixin, FixedUnbindMixin, tk.Message):
    pass

TK_EVENT_STATE_SHIFT = 1
TK_EVENT_STATE_CONTROL = 4

class GraphWrapper:

    def __init__(self, canvas, graph, node_select_callback):
        self.canvas = canvas
        self.graph = graph
        self.node_select_callback = node_select_callback

        self.labels = dict([ (node, self.label_for_node(node)) for node in graph.nodes ])
        self.lines = dict([ (node, self.lines_for_node(node)) for node in graph.nodes ])

    def label_for_node(self, node):
        label = DraggableMessage(self.canvas, text=node.name, aspect=200, cursor='hand1', takefocus=True)
        if not node.position: node.position = (random.random() * 0.8 + 0.1, random.random() * 0.8 + 0.1)
        # XXX should be more elegant way of answering the question "are we flipped?"
        if self.canvas.winfo_width() >= self.canvas.winfo_height():
            label.place({'relx': node.position[0], 'rely': node.position[1], 'anchor': 'c'})
        else:
            label.place({'relx': node.position[1], 'rely': node.position[0], 'anchor': 'c'})

        label.bind('<Button-1>', lambda event, node=node: self.on_mousedown(event, node), add=True)
        label.bind('<Configure>', lambda event, node=node: self.on_configure(event, node), add=True)
        label.bind('<<GhostRelease>>', lambda event, node=node: self.on_ghost_release(event, node), add=True)
        label.bind('<Key-Delete>', lambda event, node=node: self.on_delete(event, node), add=True)

        return label

    def lines_for_node(self, node):
        return dict([
            (parent_node, ConnectingLine(self.canvas, self.labels[parent_node], self.labels[node]))
            for parent_node in node.parent_nodes
        ])

    def highlight_node(self, node):
        for label in self.labels.values(): label['bg'] = '#DDD'
        if node:
            self.labels[node]['bg'] = 'orange'
            self.labels[node].focus()

    def on_mousedown(self, event, node):
        self.highlight_node(node)
        self.node_select_callback(node, self.labels[node])

    def on_configure(self, event, node):
        place_info = event.widget.place_info()
        # XXX should be more elegant way of answering the question "are we flipped?"
        if self.canvas.winfo_width() >= self.canvas.winfo_height():
            node.position = ( float(place_info['relx']), float(place_info['rely']) )
        else:
            node.position = ( float(place_info['rely']), float(place_info['relx']) )


    def on_delete(self, event, node):
        """<Delete> disconnects a node from the graph, connects it parents to its children,
        and deletes the node.  <Shift-Delete> removes and deletes the node, but doesn't
        reconnect parents and children.  <Ctrl-Delete> disconnects the node but doesn't
        delete it."""
        
        parent_nodes = list(node.parent_nodes)
        child_nodes = list(node.child_nodes)
        for line in self.lines[node].values(): line.destroy()
        for parent_node in parent_nodes:
            node.del_parent(parent_node)
        for child_node in child_nodes:
            child_node.del_parent(node)
            self.lines[child_node].pop(node).destroy()
            if not event.state & TK_EVENT_STATE_SHIFT:
                for parent_node in parent_nodes: self.add_parent(parent_node, child_node)
        if not event.state & TK_EVENT_STATE_CONTROL:
            self.graph.nodes.remove(node)
            del self.labels[node]
            del self.lines[node]
            event.widget.destroy()
            self.node_select_callback(None, None)
            self.highlight_node(None)

        if len(self.graph.nodes) == 0:
            new_node = PipelineNode(name="NEW 1", position=(0.5, 0.5))
            self.graph.add_node(new_node)
            self.labels[new_node] = self.label_for_node(new_node)
            self.lines[new_node] = {}
            self.highlight_node(new_node)

    def find_node_at_position(self, x, y):
        for node, label in self.labels.items():
            nx, ny, nw, nh = _geometry(label)
            if (nx <= x <= nx + nw) and (ny <= y <= ny+nh): 
                return node

    def add_new_node(self, position=(0.5, 0.5)):
        new_node = PipelineNode(name=f"NEW {len(self.graph.nodes)+1}", position=position)
        self.graph.add_node(new_node)
        self.labels[new_node] = self.label_for_node(new_node)
        self.lines[new_node] = {}
        return new_node

    def on_ghost_release(self, event, start_node):
        xl, yl, wl, hl = _geometry(event.widget)
        other_node = self.find_node_at_position(event.x + xl, event.y + yl)
        if other_node is None:
            position = (event.x + xl) / self.canvas.winfo_width(), (event.y + yl) / self.canvas.winfo_height()
            other_node = self.add_new_node(position)
        elif other_node == start_node:
            return
        elif start_node in other_node.parent_nodes:
            other_node.del_parent(start_node)
            self.lines[other_node].pop(start_node).destroy()
            return
        elif other_node in start_node.parent_nodes:
            start_node.del_parent(other_node)
            self.lines[start_node].pop(other_node).destroy()
            self.node_select_callback(start_node, self.labels[start_node])
            return

        if start_node.is_ancestor_of(other_node):
            self.add_parent(start_node, other_node)
        elif other_node.is_ancestor_of(start_node):
            self.add_parent(other_node, start_node)
        elif (event.x > 0) if self.canvas.winfo_width() > self.canvas.winfo_height() else (event.y > 0):
            self.add_parent(start_node, other_node)
        else:
            self.add_parent(other_node, start_node)

        self.highlight_node(other_node)
        self.node_select_callback(other_node, self.labels[other_node])

    def add_parent(self, parent_node, child_node):
        if parent_node not in child_node.parent_nodes:
            child_node.add_parent(parent_node)
            self.lines[child_node][parent_node] = ConnectingLine(self.canvas, self.labels[parent_node], self.labels[child_node])

    def destroy(self):
        for node_lines in self.lines.values():
            for line in node_lines.values():
                line.destroy()
        for label in self.labels.values():
            label.destroy()

class ConfiguratorWrapper:

    config_subframe = None
    preview_subframe = None

    def __init__(self, frame, node, label):
        self.frame = frame
        self.node = node
        self.label = label

        self.name_var = tk.StringVar(self.frame, value=node.name)
        tk.Entry(self.frame, textvariable=self.name_var, font=('Helvetica', 16, 'bold')).grid(row=0, sticky=tk.EW)
        self.name_var.trace("w", self.name_changed_callback)

        self.show_config_subframe()
        self.show_preview_subframe()

    def show_config_subframe(self):
        if self.config_subframe: self.config_subframe.destroy()
        if self.node.plugin:
            self.config_subframe = PluginConfigurator(self.frame, self.node.plugin, self.config_change_callback).frame
        else:
            self.config_subframe = PluginChooserFrame(self.frame, "Choose Plugin", self.choose_plugin)
        self.config_subframe.grid(row=1, sticky=tk.NSEW)

    def show_preview_subframe(self):
        if self.preview_subframe: self.preview_subframe.destroy()
        if isinstance(self.node.result, (dd.DataFrame, pd.DataFrame)):
            self.preview_subframe = DataFramePreview(self.frame, self.node.result).frame
        elif self.node.output:
            self.preview_subframe = tk.Text(self.frame, bg='indian red')
            self.preview_subframe.replace("1.0", tk.END, self.node.output)
        else:
            self.preview_subframe = tk.Frame(self.frame)

        self.preview_subframe.grid(row=2, column=0, sticky=tk.NSEW)

    def name_changed_callback(self, *_):
        name = self.name_var.get()
        self.node.name = name
        self.label['text'] = name

    def config_change_callback(self, *_):
        self.node.mark_dirty()
        self.node.prerun()
        self.show_preview_subframe()

    def choose_plugin(self, plugin_class):
        self.node.plugin = plugin_class()
        self.node.is_dirty = True
        self.show_config_subframe()

class ButtonMenu:

    def __init__(self, tk_parent, buttons):
        self.frame = tk.Frame(tk_parent)
        for button_number, (button_label, button_command) in enumerate(buttons):
            tk.Button(self.frame, text=button_label, command=button_command).grid(row=0, column=button_number, sticky=tk.EW)
        self.frame.grid(sticky=tk.NSEW)


class MainWindow:

    graph_wrapper = None
    preview_frame = None
   
    def __init__(self, tk_parent, config_filename=None):
        self.tk_parent = tk_parent

        ButtonMenu(tk_parent, [
            ( "New Config", self.config_new ),
            ( "Load Config", self.config_load ),
            ( "Save Config", self.config_save ),
            ( "Export Config", self.config_export ),
            ( "New Node", self.node_new ),
            #( "Delete Node", self.node_delete ),
            #( "Duplicate Node", self.node_duplicate ),
            ( "Run", self.program_run ),
            ( "Exit", self.program_exit ),
        ])

        self.frame = tk.Frame(tk_parent)
        self.frame.grid(sticky=tk.NSEW)

        self.canvas = FlippyCanvas(self.frame, bg='skyblue')
        self.subframe = tk.Frame(self.frame)
        self.subframe.columnconfigure(0, weight=1)
        self.subframe.rowconfigure(0, weight=0)
        self.subframe.rowconfigure(1, weight=0)
        self.subframe.rowconfigure(2, weight=1)

        self.frame.bind('<Configure>', self.on_frame_configure, add=True)

        if config_filename:
            self.config_load(config_filename)
        else:
            self.config_new()

    def config_new(self):
        self.config_filename = None
        if self.graph_wrapper: self.graph_wrapper.destroy()
        self.graph = PipelineGraph()
        new_node = PipelineNode(name="NEW 1", position=(0.25, 0.5))
        self.graph.add_node(new_node)
        self.graph_wrapper = GraphWrapper(self.canvas, self.graph, self.node_select)
        self.node_select(None, None)

    def config_load(self, filename=None):
        if not filename:
            filename = filedialog.askopenfilename(filetypes=[(".INI Config File", "*.ini")])
        if not filename: return
        self.config_filename = filename
        if self.graph_wrapper: self.graph_wrapper.destroy()
        self.graph = read_config(filename)
        self.graph_wrapper = GraphWrapper(self.canvas, self.graph, self.node_select)
        self.node_select(None, None)

    def config_save(self, filename=None):
        if not filename:
            filename = filedialog.asksaveasfilename(
                initialfile = self.config_filename,
                filetypes=[(".INI Config File", "*.ini")]
            )
        if not filename: return
        write_config(self.graph, filename)

    def config_export(self, filename=None):
        if not filename:
            if self.config_filename:
                initialfile = self.config_filename.removesuffix('.ini') + '.dot'
            else:
                initialfile = None
            filename = filedialog.asksaveasfilename(
                initialfile = initialfile,
                filetypes=[("Graphviz File", "*.dot")]
            )
        if not filename: return
        export_config_graphviz(self.graph, filename)
        pass

    def node_new(self):
        self.graph_wrapper.add_new_node()

    def node_delete(self):
        pass

    def node_duplicate(self):
        pass

    def program_run(self):
        self.graph.run()

    def program_exit(self):
        if messagebox.askokcancel("Exit", "Exit CountESS?"):
            self.tk_parent.quit()

    def node_select(self, node, label):
        for widget in self.subframe.winfo_children():
            widget.destroy()
        if node:
            node.prepare()
            node.prerun()
            ConfiguratorWrapper(self.subframe, node, label)
        else:
            tk.Label(self.subframe, text=f"CountESS {VERSION}", font=('Helvetica', 20, 'bold')).grid(row=2, sticky=tk.NSEW)

    def node_update(self, node):
        if self.preview_frame: self.preview_frame.destroy()
        if node.plugin:
            node.prepare()
            node.prerun()

    def change_callback(self, _):
        self.selected_node.mark_dirty()
        self.node_update(self.selected_node)

    def on_frame_configure(self, event):
        """Swaps layout around when the window goes from landscape to portrait"""
        print(f"CONFIGURE {event.width} {event.height}")
        if event.width > event.height:
            x = event.width // 5
            self.canvas.place(x=0, y=0, w=x, h=event.height)
            self.subframe.place(x=x, y=0, w=event.width - x, h=event.height)
        else:
            y = event.height // 4
            self.canvas.place(x=0,y=0,w=event.width, h=y)
            self.subframe.place(x=0, y=y, w=event.width, h=event.height-y)

def main():
    try:
        import ttkthemes  # type:ignore
        root = ttkthemes.ThemedTk()
        themes = set(root.get_themes())
        for t in ["winnative", "aqua", "ubuntu", "clam"]:
            if t in themes:
                root.set_theme(t)
    except ImportError:
        root = tk.root()
        # XXX some kind of ttk style setup goes here

    root.title(f"CountESS {VERSION}")
    root.rowconfigure(0, weight=0)
    root.rowconfigure(1, weight=1)
    root.columnconfigure(0, weight=1)

    MainWindow(root, sys.argv[1] if len(sys.argv) > 1 else None)

    root.mainloop()



if __name__ == "__main__":
    main()
