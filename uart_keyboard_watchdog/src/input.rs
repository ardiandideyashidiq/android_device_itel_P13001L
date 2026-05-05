use std::ffi::CStr;
use std::fs::{self, File};
use std::io;
use std::os::fd::AsRawFd;
use std::os::raw::{c_char, c_int, c_ulong};
use std::path::PathBuf;

const INPUT_DIR: &str = "/dev/input";
const DEVICE_NAME_BUFFER_LEN: usize = 256;
const SWITCH_STATE_BUFFER_LEN: usize = 8;
const SW_KEYPAD_SLIDE: usize = 0x0a;

const IOC_NRBITS: u32 = 8;
const IOC_TYPEBITS: u32 = 8;
const IOC_SIZEBITS: u32 = 14;

const IOC_NRSHIFT: u32 = 0;
const IOC_TYPESHIFT: u32 = IOC_NRSHIFT + IOC_NRBITS;
const IOC_SIZESHIFT: u32 = IOC_TYPESHIFT + IOC_TYPEBITS;
const IOC_DIRSHIFT: u32 = IOC_SIZESHIFT + IOC_SIZEBITS;

const IOC_READ: u32 = 2;

unsafe extern "C" {
    fn ioctl(fd: c_int, request: c_ulong, ...) -> c_int;
}

/// Handle to the dock input device.
pub(crate) struct InputMonitor {
    path: PathBuf,
    file: File,
}

impl InputMonitor {
    /// Find the named input device under `/dev/input`.
    pub(crate) fn discover(name: &str) -> io::Result<Option<Self>> {
        for entry in fs::read_dir(INPUT_DIR)? {
            let entry = entry?;
            let file_name = entry.file_name();
            let file_name = file_name.to_string_lossy();
            if !file_name.starts_with("event") {
                continue;
            }

            let path = entry.path();
            let file = File::open(&path)?;
            if device_name(&file)?.as_deref() == Some(name) {
                return Ok(Some(Self { path, file }));
            }
        }

        Ok(None)
    }

    /// Read the current dock switch state.
    pub(crate) fn current_switch_state(&self) -> io::Result<bool> {
        current_switch_state(&self.file)
    }

    /// Check whether the backing device node still exists.
    pub(crate) fn is_still_present(&self) -> bool {
        self.path.exists()
    }
}

fn device_name(file: &File) -> io::Result<Option<String>> {
    let mut buffer = [0 as c_char; DEVICE_NAME_BUFFER_LEN];
    // SAFETY: `ioctl` writes into the provided fixed-size buffer.
    let result = unsafe {
        ioctl(
            file.as_raw_fd(),
            eviocgname(DEVICE_NAME_BUFFER_LEN as u32),
            buffer.as_mut_ptr(),
        )
    };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }

    // SAFETY: the kernel returns a NUL-terminated device name in `buffer`.
    let name = unsafe { CStr::from_ptr(buffer.as_ptr()) };
    Ok(name.to_str().ok().map(str::to_owned))
}

fn current_switch_state(file: &File) -> io::Result<bool> {
    let mut buffer = [0_u8; SWITCH_STATE_BUFFER_LEN];
    // SAFETY: `ioctl` writes into the provided fixed-size buffer.
    let result = unsafe {
        ioctl(
            file.as_raw_fd(),
            eviocgsw(SWITCH_STATE_BUFFER_LEN as u32),
            buffer.as_mut_ptr(),
        )
    };
    if result < 0 {
        return Err(io::Error::last_os_error());
    }

    let byte = SW_KEYPAD_SLIDE / 8;
    let bit = SW_KEYPAD_SLIDE % 8;
    Ok((buffer[byte] & (1 << bit)) != 0)
}

const fn ioc(dir: u32, ty: u8, nr: u8, size: u32) -> c_ulong {
    ((dir << IOC_DIRSHIFT)
        | ((ty as u32) << IOC_TYPESHIFT)
        | ((nr as u32) << IOC_NRSHIFT)
        | (size << IOC_SIZESHIFT)) as c_ulong
}

const fn eviocgname(len: u32) -> c_ulong {
    ioc(IOC_READ, b'E', 0x06, len)
}

const fn eviocgsw(len: u32) -> c_ulong {
    ioc(IOC_READ, b'E', 0x1b, len)
}
