#
# Copyright (C) 2026 The LineageOS Project
#
# SPDX-License-Identifier: Apache-2.0
#

# Inherit from those products. Most specific first.
$(call inherit-product, $(SRC_TARGET_DIR)/product/core_64_bit_only.mk)
$(call inherit-product, $(SRC_TARGET_DIR)/product/full_base_telephony.mk)

# Inherit some common Lineage stuff.
$(call inherit-product, vendor/lineage/config/common_full_tablet.mk)

# Inherit from P13001L device
$(call inherit-product, device/itel/P13001L/device.mk)

PRODUCT_NAME := lineage_P13001L
PRODUCT_DEVICE := P13001L
PRODUCT_MANUFACTURER := ITEL
PRODUCT_BRAND := Itel
PRODUCT_MODEL := itel P13001L

PRODUCT_GMS_CLIENTID_BASE := android-transsion

PRODUCT_BUILD_PROP_OVERRIDES += \
    BuildDesc="sys_mssi_t_64_cn_armv82-user 14 UP1A.231005.007 1728750305 release-keys" \
    BuildFingerprint=Itel/P13001L-GL/itel-P13001L:14/UP1A.231005.007/1728750305:user/release-keys \
    DeviceName=itel-P13001L \
    DeviceProduct=itel-P13001L \
    SystemDevice=itel-P13001L \
    SystemName=P13001L-GL

# Default to landscape + enable auto-rotation
PRODUCT_PRODUCT_PROPERTIES += \
    ro.setupwizard.rotation_locked=false \
    persist.wm.enable_taskbar=true \

# Time
LINEAGE_VERSION_APPEND_TIME_OF_DAY := true

# Lunaris
PRODUCT_PRODUCT_PROPERTIES += \
    ro.lunaris.maintainer=R \

# Axion
PRODUCT_PRODUCT_PROPERTIES += \
    persist.sys.perf.scroll_opt = true \
    persist.sys.perf.scroll_opt.heavy_app = 2

WITH_GAPPS := true
WITH_GMS := true

# Ship Basic Call Recorder App
WITH_BCR := true

# Surface flinger boosting (Smoother scrolling, fewer frame drops but Keeps CPU slightly “awake”)
SURFACE_FLINGER_BOOST := true

TARGET_BOOT_ANIMATION_RES := 1080

TARGET_SUPPORTED_REFRESH_RATES := 60

# Animation fix for mtk devices 
PERF_ANIM_OVERRIDE := true

# Enable blur effects
TARGET_ENABLE_BLUR := true

# Enable AxionFx
TARGET_INCLUDE_AXFX := true

# Camera information (multiple sensors supported)
AXION_CAMERA_REAR_INFO := 13
AXION_CAMERA_FRONT_INFO := 8

# Maintainer name (underscores become spaces in the UI)
AXION_MAINTAINER := R

# Processor name (underscores become spaces)
AXION_PROCESSOR := Mediatek Helio G99

TARGET_INCLUDES_LOS_PREBUILTS := true
