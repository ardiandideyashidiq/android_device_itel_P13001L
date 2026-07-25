/*
 * keyboard_dock_watchdogd — UART dock keyboard attach/detach monitor.
 *
 * The kernel module mid_uart_dock.ko creates a mid_input evdev switch device
 * (SW_KEYPAD_SLIDE) when the tablet detects a hardware keyboard dock via GPIO.
 * This daemon watches for that device, reads the switch state, and sets the
 * Android property persist.vendor.uart.dock to 1 (attached) or 0 (detached).
 *
 * The init property trigger in uart_keyboard.rc then starts the proprietary
 * mid_uart_dock daemon (UART/serio bridge) when attached, or stops it when
 * detached. This replaces the Rust uart-keyboard-watchdog and the AOSP
 * framework-based dock detection.
 *
 * Both attach and detach are handled: poll() blocks on the evdev fd. When the
 * device is physically removed (undocked), the kernel unregisters it, poll()
 * returns POLLHUP/POLLERR, and the daemon sets the property to 0 before
 * entering the outer rediscovery loop.
 */

#include <android/log.h>
#include <sys/system_properties.h>

#include <linux/input.h>
#include <linux/limits.h>

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "DockEvdevMonitor", __VA_ARGS__)
#define LOGW(...) __android_log_print(ANDROID_LOG_WARN, "DockEvdevMonitor", __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, "DockEvdevMonitor", __VA_ARGS__)

#define DEV_INPUT "/dev/input"
#define DEVICE_NAME "mid_input"
#define PROP_DOCK "persist.vendor.uart.dock"
#define RETRY_DELAY_S 3
#define MAX_RETRIES 10

static int input_fd = -1;

/* Clean exit on SIGTERM from init. Closes the evdev fd then dies. */
static void sigterm_handler(int sig) {
    (void)sig;
    LOGI("received SIGTERM, exiting");
    if (input_fd >= 0) close(input_fd);
    _exit(0);
}

/* Open an evdev node and check it is the mid_input switch device.
   Returns the fd on success, -1 if the device does not match. */
static int check_input_device(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;

    char name[256];
    if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0) {
        close(fd);
        return -1;
    }
    if (strcmp(name, DEVICE_NAME) != 0) {
        close(fd);
        return -1;
    }

    uint8_t ev_bits[EV_MAX / 8 + 1];
    if (ioctl(fd, EVIOCGBIT(0, sizeof(ev_bits)), ev_bits) < 0) {
        close(fd);
        return -1;
    }
    if (!(ev_bits[EV_SW / 8] & (1 << (EV_SW % 8)))) {
        close(fd);
        return -1;
    }

    uint8_t sw_bits[(SW_MAX / 8) + 1];
    if (ioctl(fd, EVIOCGBIT(EV_SW, sizeof(sw_bits)), sw_bits) < 0) {
        close(fd);
        return -1;
    }
    if (!(sw_bits[SW_KEYPAD_SLIDE / 8] & (1 << (SW_KEYPAD_SLIDE % 8)))) {
        close(fd);
        return -1;
    }

    return fd;
}

/* Scan /dev/input/event* for the mid_input device.
   Returns the first matching fd, or -1 if not found. */
static int find_input_device(void) {
    DIR *dir = opendir(DEV_INPUT);
    if (!dir) {
        LOGE("opendir %s failed: %s", DEV_INPUT, strerror(errno));
        return -1;
    }

    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (strncmp(entry->d_name, "event", 5) != 0) continue;

        char path[PATH_MAX];
        snprintf(path, sizeof(path), "%s/%s", DEV_INPUT, entry->d_name);

        int fd = check_input_device(path);
        if (fd >= 0) {
            closedir(dir);
            LOGI("found input device: %s", path);
            return fd;
        }
    }

    closedir(dir);
    return -1;
}

/* Retry loop: poll for mid_input until it appears (up to MAX_RETRIES). */
static int wait_for_input_device(void) {
    for (int attempt = 1; attempt <= MAX_RETRIES; attempt++) {
        int fd = find_input_device();
        if (fd >= 0) return fd;
        LOGW("input device not found (attempt %d/%d), retrying in %ds...",
             attempt, MAX_RETRIES, RETRY_DELAY_S);
        sleep(RETRY_DELAY_S);
    }
    return -1;
}

/* Read the current SW_KEYPAD_SLIDE state via EVIOCGSW ioctl.
   Returns 1 (attached) or 0 (detached). */
static int get_initial_switch_state(int fd) {
    uint8_t sw_bits[(SW_MAX / 8) + 1];
    if (ioctl(fd, EVIOCGSW(sizeof(sw_bits)), sw_bits) < 0) {
        LOGW("EVIOCGSW failed: %s", strerror(errno));
        return 0;
    }
    return (sw_bits[SW_KEYPAD_SLIDE / 8] >> (SW_KEYPAD_SLIDE % 8)) & 1;
}

int main(void) {
    signal(SIGTERM, sigterm_handler);

    while (1) {
        /* Outer loop: wait for mid_input to appear (boot or re-dock). */
        input_fd = wait_for_input_device();
        if (input_fd < 0) {
            LOGE("no device after %d attempts, sleeping %ds", MAX_RETRIES, RETRY_DELAY_S);
            sleep(RETRY_DELAY_S);
            continue;
        }

        int docked = get_initial_switch_state(input_fd);
        LOGI("initial dock state: %s", docked ? "attached" : "detached");
        __system_property_set(PROP_DOCK, docked ? "1" : "0");

        struct pollfd pfd = { .fd = input_fd, .events = POLLIN };
        int alive = 1;

        /* Inner loop: block on poll() for SW_KEYPAD_SLIDE events. On POLLHUP
           or ENODEV the device was removed (undock) — set property to 0 and
           fall back to the outer loop to wait for re-dock. */
        while (alive) {
            int ret = poll(&pfd, 1, -1);
            if (ret < 0) {
                if (errno == EINTR) continue;
                LOGE("poll failed: %s", strerror(errno));
                break;
            }

            if (pfd.revents & (POLLHUP | POLLERR)) {
                LOGI("device disconnected");
                __system_property_set(PROP_DOCK, "0");
                break;
            }

            struct input_event ev;
            ssize_t n = read(input_fd, &ev, sizeof(ev));
            if (n < 0) {
                LOGE("read failed: %s", strerror(errno));
                if (errno == ENODEV) __system_property_set(PROP_DOCK, "0");
                break;
            }
            if ((size_t)n != sizeof(ev)) continue;

            if (ev.type == EV_SW && ev.code == SW_KEYPAD_SLIDE) {
                LOGI("dock %s", ev.value ? "attached" : "detached");
                __system_property_set(PROP_DOCK, ev.value ? "1" : "0");
            }
        }

        close(input_fd);
        input_fd = -1;
    }
}
