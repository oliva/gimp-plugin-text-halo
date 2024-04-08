#!/usr/bin/env python3
import gi
gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
#gi.require_version('Gegl', '0.4')
#from gi.repository import Gegl
from gi.repository import GObject
from gi.repository import GLib

#import os
import sys

'''
A Python plugin to add halo behind a text layer.
'''

# define the plugin
class TextHaloPlugin (Gimp.PlugIn):
	# Parameters
	__gproperties__ = dict()
	size =     GObject.Property(type = float,
	                            default = 0.1, minimum = 0.0,
	                            nick = "_Halo size", blurb = "Blur size / Text size")
	strength = GObject.Property(type = float,
	                            default = 1/3, minimum = 0.0, maximum = 1.0,
	                            nick = "S_trength", blurb = "1 - Input level maximum")

	## GimpPlugIn virtual methods ##
	def do_set_i18n(self, procname):
		return True, 'gimp30-python', None

	def do_query_procedures(self):
		return [ 'plug-in-halo' ]

	def do_create_procedure(self, name):
		procedure = Gimp.ImageProcedure.new(self, name,
		                                    Gimp.PDBProcType.PLUGIN,
		                                    self.run, None)
		procedure.set_image_types("RGB*, GRAY*");
		procedure.set_sensitivity_mask (Gimp.ProcedureSensitivityMask.DRAWABLE |
		                                Gimp.ProcedureSensitivityMask.DRAWABLES)
		procedure.set_documentation ("Text halo", #short
		                             "Creates a halo effect around text", #long
		                             name)
		procedure.set_menu_label("Text _halo...") #underscore before shortcut, ... signifies a dialog
		procedure.set_attribution("Temlin, Olivér", #name
		                          "Temlin, Olivér", #name again?
		                          "2023")  #date
		procedure.add_menu_path ("<Image>/Filters/Light and Shadow")

		procedure.add_argument_from_property(self, "size")
		procedure.add_argument_from_property(self, "strength")

		return procedure

	# Main function
	def run(self, procedure, run_mode, image, n_drawables, drawables, config, data):
		pdb = Gimp.get_pdb()

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

		size = config.get_property('size')
		strength = config.get_property('strength')
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

		errors = list()

		for layer in layers:
			if not isinstance(layer, Gimp.TextLayer):
				errors.append(layer.get_name())
				continue
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
			if halo is None:
				# Bail if failed to copy layer
				image.undo_group_end()
				Gimp.context_pop()
				Gimp.displays_flush()
				return procedure.new_return_values(Gimp.PDBStatusType.EXECUTION_ERROR, GLib.Error())
			_, x, y = layer.get_offsets()
			halo.set_offsets(x, y)
			halo.set_name(name + ' halo')
			image.insert_layer(halo, group, 1)
			# This will also rasterize this layer
			halo.resize_to_image_size()
			# Add mask from alpha
			mask = halo.create_mask(Gimp.AddMaskType.ALPHA_TRANSFER)
			halo.add_mask(mask)
			# Fill with text color, then invert
			color = layer.get_color()
			Gimp.context_set_foreground(color)
			halo.fill(Gimp.FillType.FOREGROUND)
			halo.invert(linear=False)
			# Blur mask
			font_size, _ = layer.get_font_size()
			gauss_iir = pdb.lookup_procedure('plug-in-gauss-iir')
			gauss_config = gauss_iir.create_config()
			gauss_config.set_properties(
				run_mode=Gimp.RunMode.NONINTERACTIVE,
				image=image, drawable=mask,
				radius=size*font_size, horizontal=True, vertical=True)
			status = gauss_iir.run(gauss_config).index(0)
			# Correct levels on mask
			level_min = 0.047
			level_max = level_min + (1-strength) / (1+level_min)
			mask.levels(Gimp.HistogramChannel.VALUE, #channel
			            level_min, level_max, True, 1.0, #input min, max, clamp, gamma
			            0.0, 1.0, False) #out min, max, clamp
			# Apply mask
			halo.remove_mask(Gimp.MaskApplyMode.APPLY)
			# Crop to content
			autocrop_layer = pdb.lookup_procedure('plug-in-autocrop-layer')
			autocrop_config = autocrop_layer.create_config()
			autocrop_config.set_properties(
				run_mode=Gimp.RunMode.NONINTERACTIVE,
				image=image, drawable=halo)
			status = autocrop_layer.run(autocrop_config).index(0)

		# Close undo group
		image.undo_group_end()
		if errors:
			Gimp.message('Non-text layers skipped: ' + ', '.join(errors))

		# Boilerplate
		Gimp.context_pop()
		Gimp.displays_flush()
		return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

# register plugin
Gimp.main(TextHaloPlugin.__gtype__, sys.argv)
