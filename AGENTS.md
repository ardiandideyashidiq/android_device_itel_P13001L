# AGENTS.md

## Source Of Truth
- Trust `*.mk`, `Android.bp`, shell scripts, and `proprietary-files.txt` over `README.md` for build behavior.
- This tree is incomplete by itself; it inherits from `vendor/itel/P13001L/BoardConfigVendor.mk` and `vendor/itel/P13001L/P13001L-vendor.mk`.

## Key Entry Points
- Product: `infinity_P13001L`.
- Lunch choices: `infinity_P13001L-user`, `infinity_P13001L-userdebug`, `infinity_P13001L-eng`.
- Build it from the Android top-level tree with `source build/envsetup.sh && lunch infinity_P13001L-userdebug`.
- `infinity_P13001L.mk` sets `WITH_GMS := true` and `WITH_GAPPS := true`, so the GMS path is the default here.
- `device.mk` is the main product config; `BoardConfig.mk` defines partition, kernel, AVB, sepolicy, and Wi-Fi behavior.

## Non-Obvious Build Rules
- `WITH_GMS=true` changes filesystem setup in `BoardConfig.mk`: all SSI/Treble partitions become `erofs`; without it, `product` and `system_ext` stay `ext4` while Treble partitions stay `erofs`.
- `WITH_GMS=true` also pulls `vendor/infinity/config/BoardConfigReservedSize.mk`.
- Kernel artifacts are read from `device/itel/P13001L-kernel`; `BoardConfig.mk` expects `modules/vendor_ramdisk/modules.load`, `modules/vendor_ramdisk/modules.load.recovery`, and `modules/vendor_dlkm/modules.load` to exist there.
- `rootdir/Android.bp` aliases several `mt8781` prebuilts to `mt6789` source files; do not rename those files casually.
- `vendor_logtag.mk` is included from `device.mk` and only changes log tags by build variant (`I` on `eng`, `S` otherwise).

## Repo Scripts
- `./setup-makefiles.py` regenerates vendor makefiles via `extract-files.py --regenerate_makefiles`.
- `python3 compare-props.py` compares `configs/properties/system.prop` and `configs/properties/vendor.prop` against the stock dump; `--apply` rewrites those files in place.
- `compare-props.py` defaults to `/home/rd/temp/dumpyara/P13001L-M131-U-GL-250305V19` as the dump root.
- `python update-sha1sums.py -c` strips blob hashes from `proprietary-files.txt`; without `-c`, it recalculates hashes from `../../../vendor/itel/P13001L/proprietary`.
- `vendor_logtag.mk` is only a property overlay; it does not add packages or files.

## Layout
- `configs/` holds props, audio, media, wifi, thermal, seccomp, permissions, and VINTF XMLs.
- `rootdir/` holds init/fstab prebuilts and the `init.insmod.sh` vendor script.
- `sepolicy/` is split into `public/`, `private/`, and `vendor/`.
- `overlay/` and `overlay-lineage/` contain resource overlays.

## Editing Notes
- `proprietary-files.txt` comments with `- from` are the entries that `update-sha1sums.py` hashes.
- The blob list is based on the stock dump named at the top of `proprietary-files.txt` unless an entry is pinned.
- The OTA device assert names are `itel-P13001L`, `P13001L`, and `P13001L-GL`.
