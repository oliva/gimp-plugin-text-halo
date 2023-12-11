#!/usr/bin/env python3
import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
from gi.repository import GObject
from gi.repository import GLib
import sys


'''
A Python plugin to add halo behind a (text) layer.
'''

# Main function
def text_halo(procedure, run_mode, image, n_drawables, drawables, args, data):
	pdb = Gimp.get_pdb()
	# Boilerplate
	config = procedure.create_config()
	config.begin_run(image, run_mode, args)

	if run_mode == Gimp.RunMode.INTERACTIVE:
		GimpUi.init('plug-in-halo')
		dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config)
		dialog.fill(None)
		if not dialog.run():
			dialog.destroy()
			config.end_run(Gimp.PDBStatusType.CANCEL)
			return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
		else:
			dialog.destroy()

	sigma = config.get_property('sigma')
	level_min = config.get_property('level_min')
	level_gamma = config.get_property('level_gamma')
	level_max = config.get_property('level_max')
	layers = image.list_selected_layers()

	Gimp.context_push()

	# list of actions
	# - create group
	# - move layer in group
	# - duplicate layer to group
	# - rasterize new layer
	# - layer to image size
	# - alpha to mask
	# - invert colors
	# - select mask
	# - gaussian blur
	# - levels
	# - apply mask
	# - crop layer to content

	# Compress actions to one undo event
	image.undo_group_start()

	for layer in layers:
		# Select current layer so insert is placed correctly
		image.set_selected_layers([layer])
		name = layer.get_name()
		layer.set_name(name + ' text')
		parentLayer = layer.get_parent()

		# Create new layer group
		group = Gimp.Layer.group_new(image)
		group.set_name(name)
		# Insert the layer group above the current layer
		image.insert_layer(group, parentLayer, -1)
		# Put the layer in the group
		image.reorder_item(layer, group, 0)

		# Create the halo layer
		halo = Gimp.Layer.copy(layer)
		_, x, y = layer.get_offsets()
		halo.set_offsets(x, y)
		halo.set_name(name + ' halo')
		image.insert_layer(halo, group, 1)
		# This will also rasterize this layer
		halo.resize_to_image_size()
		# Add mask from alpha
		mask = halo.create_mask(Gimp.AddMaskType.ALPHA_TRANSFER)
		halo.add_mask(mask)
		# Invert image
		halo.invert(linear=False) # TODO optionally get a color and fill
		# Blur mask
		pdb.run_procedure('plug-in-gauss', [Gimp.RunMode.NONINTERACTIVE, image, mask, sigma, sigma, 0])
		# Correct levels on mask
		pdb.run_procedure('gimp-drawable-levels', [mask, Gimp.HistogramChannel.VALUE, level_min, level_max, False, level_gamma, 0.0, 1.0, False])
		# Apply mask
		halo.remove_mask(Gimp.MaskApplyMode.APPLY)
		# Crop to content
		pdb.run_procedure('plug-in-autocrop-layer', [Gimp.RunMode.NONINTERACTIVE, image, halo])

		# Update displays
		Gimp.displays_flush()

	# Close undo group
	image.undo_group_end()

	# Boilerplate
	Gimp.displays_flush()
	Gimp.context_pop()
	config.end_run(Gimp.PDBStatusType.SUCCESS)
	return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

# define the plugin
class TextHaloPlugin (Gimp.PlugIn):
	# Parameters
	sigma = GObject.Property(type = float,
	                         default = 3.0, minimum = 0.0,
	                         nick = "Halo _size", blurb = "Blur sigma")
	level_min = GObject.Property(type = float,
	                             default = 0.0, minimum = 0.0, maximum = 1.0,
	                             nick = "_Shrink", blurb = "Level minimum")
	level_gamma = GObject.Property(type = float,
	                               default = 0.3, minimum = 0.10, maximum = 10.0,
	                               nick = "_Gamma", blurb = "Level gamma")
	level_max = GObject.Property(type = float,
	                             default = 0.3, minimum = 0.0, maximum = 1.0,
	                             nick = "_Opaque %", blurb = "Level maximum")

	## GimpPlugIn virtual methods ##
	def do_set_i18n(self, procname):
		return True, 'gimp30-python', None

	def do_query_procedures(self):
		return [ 'plug-in-halo' ]

	def do_create_procedure(self, name):
		procedure = Gimp.ImageProcedure.new(self, name,
		                                    Gimp.PDBProcType.PLUGIN,
		                                    text_halo, None)
		procedure.set_sensitivity_mask (Gimp.ProcedureSensitivityMask.NO_IMAGE)
		procedure.set_documentation ("Text halo", #short
		                             "Creates a halo effect around text", #long
		                             name)
		procedure.set_menu_label("Text _halo...") #underscore before shortcut, ... signifies a dialog
		procedure.set_attribution("Temlin, Olivér", #name
		                          "Temlin, Olivér", #name again?
		                          "2023")  #date
		procedure.add_menu_path ("<Image>/Filters/Light and Shadow")

		procedure.add_argument_from_property(self, "sigma")
		procedure.add_argument_from_property(self, "level_min")
		procedure.add_argument_from_property(self, "level_gamma")
		procedure.add_argument_from_property(self, "level_max")

		return procedure

# register plugin
Gimp.main(TextHaloPlugin.__gtype__, sys.argv)
