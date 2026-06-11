use std::ffi::CString;
use std::fmt;
use std::os::raw::{c_char, c_int};

const ANDROID_LOG_INFO: c_int = 4;
const ANDROID_LOG_WARN: c_int = 5;

#[link(name = "log")]
unsafe extern "C" {
    fn __android_log_write(prio: c_int, tag: *const c_char, text: *const c_char) -> c_int;
}

/// Minimal logger backed by `__android_log_write`.
pub(crate) struct Logger {
    tag: CString,
}

impl Logger {
    /// Build a logger for the supplied tag.
    pub(crate) fn new(tag: &str) -> Self {
        let sanitized = sanitize(tag);
        Self {
            tag: CString::new(sanitized).expect("sanitized log tag should not contain NUL"),
        }
    }

    /// Emit an INFO log line.
    pub(crate) fn info(&self, message: impl fmt::Display) {
        self.emit(ANDROID_LOG_INFO, message);
    }

    /// Emit a WARN log line.
    pub(crate) fn warn(&self, message: impl fmt::Display) {
        self.emit(ANDROID_LOG_WARN, message);
    }

    fn emit(&self, priority: c_int, message: impl fmt::Display) {
        let formatted = message.to_string();
        let sanitized = sanitize(&formatted);
        let c_message = CString::new(sanitized).expect("sanitized log message should not contain NUL");
        // SAFETY: both pointers come from NUL-free `CString`s and stay alive for the call.
        unsafe {
            __android_log_write(priority, self.tag.as_ptr(), c_message.as_ptr());
        }
    }
}

fn sanitize(value: &str) -> String {
    value.replace('\0', "?")
}
