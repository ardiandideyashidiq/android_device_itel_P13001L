use std::ffi::CString;
use std::os::raw::{c_char, c_int};

const ANDROID_LOG_INFO: c_int = 4;
const ANDROID_LOG_WARN: c_int = 5;

#[link(name = "log")]
unsafe extern "C" {
    fn __android_log_write(prio: c_int, tag: *const c_char, text: *const c_char) -> c_int;
}

pub(crate) struct Logger {
    tag: CString,
}

impl Logger {
    pub(crate) fn new(tag: String) -> Self {
        let sanitized = sanitize(&tag);
        Self {
            tag: CString::new(sanitized).expect("sanitized log tag should not contain NUL"),
        }
    }

    pub(crate) fn info(&self, message: &str) {
        self.emit(ANDROID_LOG_INFO, message);
    }

    pub(crate) fn warn(&self, message: &str) {
        self.emit(ANDROID_LOG_WARN, message);
    }

    fn emit(&self, priority: c_int, message: &str) {
        let sanitized = sanitize(message);
        let c_message = CString::new(sanitized).expect("sanitized log message should not contain NUL");
        unsafe {
            __android_log_write(priority, self.tag.as_ptr(), c_message.as_ptr());
        }
    }
}

fn sanitize(value: &str) -> String {
    value.replace('\0', "?")
}
