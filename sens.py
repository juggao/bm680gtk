# Gtk BME680 Sensor display
# reads from /dev/ttyACM0 connected to Arduino

import gi 
import threading

from queue import Queue
import io, os
from serial import Serial
from parse import parse

ser = Serial('/dev/ttyACM0', 115200)  # open serial port
print(ser.name)


gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GObject, GLib, Pango

sensor_list = [
    ("Temperature", 0, "°C"),
    ("Humidity", 0, "%"),
    ("Pressure", 0, "hPa"),
    ("Gas", 0, "kOhm")
]

TEMP = 0.00
HUMIDITY = 0.00
PRESSURE = 0.00
GAS = 0.00

UPDATE_TIMEOUT = 0.3 # in seconds

_lock = threading.Lock()
def info(*args):
    with _lock:
        print("%s %s" % (threading.current_thread(), " ".join(map(str, args))))


class Updater:
    def __init__(self):
        self._task_id = 0
        self._queue = Queue(maxsize=100) #NOTE: GUI blocks if queue is full
        t = threading.Thread(target=self._work)
        t.daemon = True
        t.start()

    def _work(self):
        global TEMP, HUMIDITY, PRESSURE, GAS
        # executed in background thread
        #opener = urllib2.build_opener()
        for task_id, done, args in iter(self._queue.get, None):
            #info('received task', task_id)
            try: # do something blocking e.g., urlopen()
                ln = ser.readline()
                s = ln.decode('utf-8')
                res = parse('Temperature = {} *C\r\n', s)
                if res is not None:
                    TEMP = float(res[0])
                res = parse('Humidity = {} %\r\n', s)
                if res is not None:
                    HUMIDITY = float(res[0])
                res = parse('Pressure = {} hPa\r\n', s)
                if res is not None:
                    PRESSURE = float(res[0])
                res = parse('Gas = {} KOhms\r\n', s)
                if res is not None:
                    GAS = float(res[0])
                #print(GAS)
            except IOError:
                pass # ignore errors

            # signal task completion; run done() in the main thread
            GLib.idle_add(done, *((task_id,) + args))

    def add_update(self, callback, *args):
        # executed in the main thread
        self._task_id += 1
        #info('sending task ', self._task_id)
        self._queue.put((self._task_id, callback, args))

#GObject.threads_init() # init threads?

class TreeViewFilterWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="BME680 Sensors")
        self.set_border_width(5)
        self.set_default_size(1000, 300)

        # Setting up the self.grid in which the elements are to be positionned
        page_s    = Gtk.Adjustment(lower=100, page_size=600) 
      
        self.grid = Gtk.Grid(hexpand=True, vexpand=True)
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_homogeneous(True)
        self.add(self.grid)
        self.grid.set_vexpand(True)
        self.grid.set_hexpand(True)
        # Creating the ListStore model
        self.sensor_liststore = Gtk.ListStore(str, float, str)
        for sensor_ref in sensor_list:
            self.sensor_liststore.append(list(sensor_ref))
        self.current_filter_sensor = None

        # Creating the filter, feeding it with the liststore model
        self.sensor_filter = self.sensor_liststore.filter_new()
        # setting the filter function, note that we're not using the
        self.sensor_filter.set_visible_func(self.sensor_filter_func)

        # creating the treeview, making it use the filter as a model, and adding the columns
        self.treeview = Gtk.TreeView(model=self.sensor_filter)
        for i, column_title in enumerate(
            ["Sensor", "Value", "Unit"]
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            self.treeview.append_column(column)

        # creating buttons to filter by unit, and setting up their events
        self.buttons = list()
        for unit in ["°C", "%", "hPa", "kOhm", "None"]:
            button = Gtk.Button(label=unit)
            self.buttons.append(button)
            button.connect("clicked", self.on_selection_button_clicked)

        # setting up the layout, putting the treeview in a scrollwindow, and the buttons in a row
        self.scrollable_treelist = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        #self.scrollable_treelist.pack_start(self.scrollable_treelist, True, True, 0)
        #self.scrollable_treelist.set_policy(Gtk.POLICY_AUTOMATIC, Gtk.POLICY_AUTOMATIC) # only display scroll bars when required
        self.scrollable_treelist.set_vexpand(True)
        self.scrollable_treelist.set_hexpand(True)
        self.grid.attach(self.scrollable_treelist, 0, 0, 8, 10)
        self.grid.attach_next_to(
            self.buttons[0], self.scrollable_treelist, Gtk.PositionType.BOTTOM, 1, 1
        )
        for i, button in enumerate(self.buttons[1:]):
            self.grid.attach_next_to(
                button, self.buttons[i], Gtk.PositionType.RIGHT, 1, 1
            )
        self.scrollable_treelist.add(self.treeview)
        self.scrollable_treelist.override_font(Pango.FontDescription('Dejavu Sans Mono 40'))
       
        #fontdesc = Pango.FontDescription()
        #fontdesc.set_family("Dejavu Sans Mono")
        #fontdesc.set_size((int)(40 * Pango.SCALE))

      
        #attr_list = Pango.AttrList()
        #attr_list.insert(Pango.AttrFontDesc (fontdesc))          
        #self.treeview.set_attributes(Pango.AttrFontDesc(fontdesc))      
       
       
        self.updater = Updater()
        self._update_id = 0
        self.show_all()
        self.update()      
    
    def update(self):
        if self._update_id is not None: 
            GLib.source_remove(self._update_id)

        self.updater.add_update(self.done_updating) # returns immediately
        # call in UPDATE_TIMEOUT seconds
        self._update_id = GLib.timeout_add(
            int(UPDATE_TIMEOUT*1000), self.update)

    def done_updating(self, task_id):
        #info('done updating', task_id)
        self.sensor_liststore[0][1]=TEMP
        self.sensor_liststore[1][1]=HUMIDITY
        self.sensor_liststore[2][1]=PRESSURE
        self.sensor_liststore[3][1]=GAS

    def sensor_filter_func(self, model, iter, data):
        """Tests if the sensor in the row is the one in the filter"""
        if (
            self.current_filter_sensor is None
            or self.current_filter_sensor == "None"
        ):
            return True
        else:
            return model[iter][2] == self.current_filter_sensor

    def on_selection_button_clicked(self, widget):
        """Called on any of the button clicks"""
        # we set the current sensor filter to the button's label
        self.current_filter_sensor = widget.get_label()
        print("%s sensor selected!" % self.current_filter_sensor)
        # we update the filter, which updates in turn the view
        self.sensor_filter.refilter()


win = TreeViewFilterWindow()
win.connect("destroy", Gtk.main_quit)
win.show_all()
Gtk.main()
