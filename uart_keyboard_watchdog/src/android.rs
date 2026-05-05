use std::ffi::CString;
use std::io;
use std::os::raw::{c_char, c_int};

use crate::config::Config;

#[link(name = "c")]
unsafe extern "C" {
    fn __system_property_set(name: *const c_char, value: *const c_char) -> c_int;
}

/// Apply the dock state to the configured Android property.
pub(crate) fn apply_dock_state(config: &Config, attached: bool) -> io::Result<()> {
    let value = if attached { "1" } else { "0" };
    setprop(&config.persist_property, value)
}

fn setprop(name: &str, value: &str) -> io::Result<()> {
    let name = CString::new(name)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "property name contains NUL"))?;
    let value = CString::new(value)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "property value contains NUL"))?;

    // SAFETY: both pointers come from NUL-free `CString`s and stay alive for the call.
    let result = unsafe { __system_property_set(name.as_ptr(), value.as_ptr()) };
    if result == 0 {
        return Ok(());
    }

    Err(io::Error::last_os_error())
}
