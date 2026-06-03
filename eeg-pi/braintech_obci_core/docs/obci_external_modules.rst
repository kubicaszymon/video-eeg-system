External packages/modules for BCI Framework
===========================================

Every Peer can be launched in a scenario by providing its path relative to
BCI Framework install directory, full global path, and python import path. The
latter is very useful for scenario packs which come with their own peers.

You can install python package through pip or in a .deb package which will provide you with
new scenarios, peers and presets.

Creating such packages
----------------------

To create such package you need to have it formatted apropriately.

Such package should be structured like this:

* `obci-external-package-name`

  * `cmd` - entry points, scripts, gui apps etc.
  * `presets` - presets for obci gui
  * `scenarios` - folder which contains scenarios
  * `peers` - folder which contains your peers
  * `drivers` - folder which should contain your custom classes for communication with hardware

Of course if you need, you can add more folders for images, icons, additional data.
This structure is minimum which is expected by the BCI Framework to seccesfuly integrate your module.

Launch file path in your presets should be written relative to your `scenarios` folder.
