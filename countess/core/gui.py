# TK based GUI for CountESS 
import threading
import tkinter as tk
import tkinter.ttk as ttk
import ttkthemes # type:ignore
from tkinter import filedialog
import pathlib

from typing import Optional
from collections.abc import Iterable, Sequence
from functools import partial

from tkinter.scrolledtext import ScrolledText

from .plugins import BasePlugin, PluginManager

plugin_manager = PluginManager()

class _PluginFrameWrapper:
    pass

class PluginFrameWrapper(_PluginFrameWrapper):

    def __init__(self, previous_pfw: _PluginFrameWrapper, plugin_choices: Sequence[BasePlugin]):
        self.previous_pfw = previous_pfw
        self.plugin_choices = plugin_choices
        self.dataframe = None

        self.frame = ttk.Frame()
        self.subframe = None

        self.selector = ttk.Combobox(self.frame)
        self.selector['values'] = [ pp.name for pp in self.plugin_choices ]
        self.selector['state'] = 'readonly'
        self.selector.set('Select Plugin')
        self.selector.pack(fill=tk.X, padx=5, pady=5)

        self.subframe = ttk.Frame(self.frame)
        
        self.selector.bind('<<ComboboxSelected>>', self.selected)
        self.selector.pack()

    def selected(self, event: tk.Event):
        if self.subframe:
            self.subframe.destroy()

        self.plugin_selected = self.plugin_choices[self.selector.current()]

        self.subframe = ttk.Frame(self.frame)
        ttk.Label(self.subframe, text=self.plugin_selected.title).grid(row=0,columnspan=2)
        
        text = ScrolledText(self.subframe, height=5)
        text.insert('1.0', self.plugin_selected.description)
        text['state'] = 'disabled'
        text.grid(row=1,columnspan=2, sticky="ew")

        self.param_entries = {}
        if self.plugin_selected.params is not None:
            for n, (k, v) in enumerate(self.plugin_selected.params.items()):
                ttk.Label(self.subframe, text=v['label']).grid(row=n+2, column=0)
                ee = tk.Entry(self.subframe)
                self.param_entries[k] = ee
                ee.grid(row=n+2, column=1, sticky="ew")

        self.last_row = len(self.plugin_selected.params)+2

        self.add_file_button = ttk.Button(self.subframe, text="Add File", command=self.add_file_clicked)
        self.add_file_button.grid(row=self.last_row, column=0)

        self.button = tk.Button(self.subframe, text="Run", command=self.run_clicked)
        self.button.grid(row=self.last_row, column=1)

        self.subframe.pack(expand=True, pady=10, padx=10)

    def get_params(self):
        return dict( (k, ee.get()) for k, ee in self.param_entries.items() )

    def run_clicked(self, *args):
        self.button['state'] = 'disabled'
        t = threading.Thread(target=self.run)
        t.start()

    def add_file_clicked(self, *args):
        self.add_file_button['state'] = 'disabled'
        filenames = filedialog.askopenfilenames()
        for n, filename in enumerate(filenames):
            filestem = pathlib.Path(filename).stem
            ttk.Label(self.subframe, text=filename).grid(row=10+n,column=0)
            e = ttk.Entry(self.subframe)
            e.grid(row=10+n,column=1)
            e.insert(0,filestem)



        print(filename)

    def run(self):
   
        plugin = self.plugin_selected(**(self.get_params()))

        progress_window = ProgressWindow(self.frame, plugin.name)

        if self.previous_pfw is not None:
            if self.previous_pfw.dataframe is None:
                self.previous_pfw.run()
            ddf = self.previous_pfw.dataframe
        else:
            ddf = None

        try:
            self.dataframe = plugin.run_with_progress_callback(ddf, progress_window.progress_cb)
            progress_window.finished()
        except Exception as e:
            print(e)
            import traceback
            progress_window.show_output(str(e), traceback.format_exception(e))

        self.button['state'] = 'normal'


class ProgressWindow:

    def __init__(self, parent, plugin_name: str):
        self.window = tk.Toplevel()
        self.pbar = ttk.Progressbar(self.window, mode='indeterminate', length=500)
        self.pbar.pack()

        self.label = ttk.Label(self.window)
        self.label['text'] = 'Running'
        self.label.pack()

        self.text : Optional[ScrolledText] = None

    def progress_cb(self, a: int, b: int, s: Optional[str]='Running'):
        if b:
            self.pbar.stop()
            self.pbar['mode'] = 'determinate'
            self.pbar['value'] = (100 * a / b)
            self.label['text'] = f"{s} : {a} / {b}"
        else:
            self.pbar['mode'] = 'indeterminate'
            self.pbar.start()
            if a is not None:
                self.label['text'] = f"{s} : {a}"
            else:
                self.label['text'] = s

    def show_output(self, label: str, text: Iterable[str]):
        self.label['text'] = label

        self.text = ScrolledText(self.window, height=20)
        for n, t in enumerate(text, 1):
            self.text.insert(f'{n}.0', t)
        self.text['state'] = 'disabled'

        self.text.pack()

    def finished(self):
        self.label['text'] = 'Finished'
        self.pbar.stop()
        self.pbar['value'] = 100


# These classes specialize widgets instead of wrapping them wwhich isn't my favourite way
# but it seems to be clearer in this case.
# The Tkinter "master" terminology is also objectionable.

class CancelButton(tk.Button):
    def __init__(self, master, **kwargs):
        super().__init__(master, text="\u274c", width=1, highlightthickness=0, bd=0, fg="red", **kwargs)

class PluginWrapper(ttk.Frame):
    def __init__(self, master, plugin):
        super().__init__(master)
        self.plugin = plugin

        #ttk.Label(self, text=self.plugin.description).pack()
        #ttk.Separator(self, orient="horizontal").pack(fill='x')
        self.header = PluginHeader(self, plugin)
        self.config = PluginConfigurator(self, plugin)
        self.footer = PluginFooter(self, plugin)
        for w in self.winfo_children(): w.pack(fill=tk.X)
        CancelButton(self, command=self.delete).place(anchor=tk.NE, relx=1, rely=0)

    def delete(self):
        self.master.del_plugin(self)

    def run(self):
        self.footer.set_progress(42,107,"WOO")

class PluginHeader(ttk.Frame):
    def __init__(self, master, plugin):
        super().__init__(master)
        self.plugin = plugin
        ttk.Label(self, text=self.plugin.name).pack()
        ttk.Label(self, text=self.plugin.description).pack()
        ttk.Separator(self, orient="horizontal").pack()
    
class PluginConfigurator(ttk.Frame):
    def __init__(self, master, plugin):
        super().__init__(master)
        self.plugin = plugin

        self.param_entries = {}
        if self.plugin.params is not None:
            for n, (k, v) in enumerate(self.plugin.params.items()):
                ttk.Label(self, text=v['label']).grid(row=n, column=0)
                ee = tk.Entry(self)
                self.param_entries[k] = ee
                ee.grid(row=n, column=1, sticky="ew")


class LabeledProgressbar(ttk.Progressbar):

    style_data = [
        ('LabeledProgressbar.trough', {
            'children': [
                ('LabeledProgressbar.pbar', {'side': 'left', 'sticky': 'ns'}),
                ("LabeledProgressbar.label", {"sticky": ""})
            ],
            'sticky': 'nswe'
        })
    ]

    def __init__(self, master, *args, **kwargs):
        self.style = ttk.Style(master)
        # make up a new style name so we don't interfere with other LabeledProgressbars
        # and accidentally change their color or label
        self.style_name = f"_id_{id(self)}"
        self.style.layout(self.style_name, self.style_data)
        self.style.configure(self.style_name, background="green")

        kwargs['style'] = self.style_name
        super().__init__(master, *args, **kwargs)

    def update_label(self, s):
        self.style.configure(self.style_name, text=s)


class PluginFooter(ttk.Frame):
    def __init__(self, master, plugin):
        super().__init__(master)
        self.plugin = plugin

        ttk.Separator(self, orient="horizontal").pack(fill='x')
        tk.Button(self, text="RUN", fg="green", command=master.run).pack()
        self.pbar = LabeledProgressbar(self, length=500)
        self.pbar.pack()

    def set_progress(self, a,b,s="Running"):
        if b:
            self.pbar.stop()
            self.pbar['mode'] = 'determinate'
            self.pbar['value'] = (100 * a / b)
            self.pbar.update_label(f"{s} : {a} / {b}")
        else:
            self.pbar['mode'] = 'indeterminate'
            self.pbar.start()
            self.pbar.update_label(f"{s} : {a}" if a is not None else s)
                
class PluginChooser(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        for n, p in enumerate(plugin_manager.plugins):
            ttk.Button(self, text=p.name, command=partial(self.choose, p)).grid(row=n, column=0)
            ttk.Label(self, text=p.description).grid(row=n, column=1)

    def choose(self, plugin):
        self.master.add_plugin(plugin)

        

class PipelineBuilder(ttk.Notebook):
    def __init__(self, master):
        super().__init__(master)
        self.enable_traversal()

        self.add(PluginChooser(self), text="+ Add +")
        self.pack()

    def add_plugin(self, plugin):
        plugin_wrapper = PluginWrapper(self, plugin)

        index = self.index('end')-1
        self.insert(index, plugin_wrapper, text=plugin.name, sticky="ew")
        self.select(index)
        plugin_wrapper.tab_id = self.select()

    def del_plugin(self, plugin_wrapper):
        self.forget(plugin_wrapper.tab_id)
        self.select(self.index('end')-1)

class DataFramePreview(ttk.Frame):
    def __init__(self, master, ddf):
        super().__init__(master)
        self.ddf = ddf
        self.height = 10
        self.index_values = list(ddf.index)[0:1000]

        self.treeview = ttk.Treeview(self, columns=list(ddf.columns), displaycolumns='#all', height=self.height, selectmode='none')
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll_to)

        self.treeview.pack(side="left")
        self.scrollbar.pack(side="right", fill="y")

        self.set_offset(0)

    def scroll_to(self, _, x):
        x = float(x)
        if x<=0: x = 0
        if x>=1: x = 1
        self.set_offset(int((len(self.index_values)-self.height) * x))

    def set_offset(self, offset):
        # XXX horribly inefficient PoC
        for n in range(0, self.height):
            if self.treeview.exists(n): self.treeview.delete(n)
        indices = self.index_values[offset:offset+self.height]
        for n, (index, *values) in enumerate(self.ddf.loc[indices[0]:indices[-1]].itertuples()):
            self.treeview.insert('', 'end', iid=n, text=index, values=values)




class MainWindow:
    """The main plugin selection window.  This should be building a "chain" of plugins
    but for now it just has three tabs, for Input, Transform and Output plugins"""

    def __init__(self, parent):
        self.parent = parent
        notebook = ttk.Notebook(parent)

        ifw = PluginFrameWrapper(None, plugin_manager.get_input_plugins())
        tfw = PluginFrameWrapper(ifw, plugin_manager.get_transform_plugins())
        ofw = PluginFrameWrapper(tfw, plugin_manager.get_output_plugins())

        notebook.add(ifw.frame, text="Input Plugin")
        notebook.add(tfw.frame, text="Transform Plugin")
        notebook.add(ofw.frame, text="Output Plugin")
        notebook.pack(expand=True, fill=tk.BOTH)

    def quit(self):
        self.parent.destroy()


def main():
    root = ttkthemes.ThemedTk()
    root.title('CountESS')


    themes = set(root.get_themes())
    for t in ['winnative', 'aqua', 'ubuntu', 'clam']:
        if t in themes:
            root.set_theme(t)
            break

    PipelineBuilder(root)
    #MainWindow(root)
    root.mainloop()

if __name__ == '__main__':
    main()

