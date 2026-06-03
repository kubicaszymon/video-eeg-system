# -*- mode: python ; coding: utf-8 -*-
import sys
if sys.platform.startswith('darwin'):
    binaries=[('/System/Library/Frameworks/Tk.framework/Tk', 'tk'),
		       ('/System/Library/Frameworks/Tcl.framework/Tcl', 'tcl')]
else:
    binaries = []
block_cipher = None

a = Analysis(['svarog_streamer.py'],
             pathex=['.'],
             binaries=binaries,
             hiddenimports=['braintech.drivers.double_amplifier',
                             'braintech.drivers.double_amplifier.double_amplifier_peer',
                             'braintech.drivers.native_amplifier_lib',
                             'braintech.drivers.native_amplifier_lib.peers',
                             'braintech.drivers.native_amplifier_lib.peers.dummy_amplifier_peer',
                             'braintech.drivers.perun32',
                             'braintech.drivers.perun32.perun32_peer',
                             'braintech.drivers.perun8',
                             'braintech.drivers.perun8.peers',
                             'braintech.drivers.perun8.peers.perun_amplifier_peer',
                             'braintech.obci.experiment',
                             'braintech.obci.experiment.messages',
                             'braintech.obci.experiment.peers.acquisition.reusable_signal_saver_peer',
                             'distutils',
                             'engineio',
                             'engineio.async_aiohttp',
                             'engineio.async_threading',
                             'obci_p300',
                             'sentry_sdk',
                             'sklearn.utils._cython_blas',
                             'socketio',
                             'usb1',
             ],
             hookspath=['hooks'],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)


pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='svarog_streamer',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True,
          icon='braintech.ico')


coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,

               strip=False,
               upx=True,
               upx_exclude=[],
               name='svarog_streamer')
