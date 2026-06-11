//! Dock keyboard watchdog service.
//!
//! Watches the `mid_input` device and keeps the dock state property in sync.

mod android;
mod app;
mod config;
mod controller;
mod input;
mod logging;

use std::process::ExitCode;

use crate::app::run;
use crate::config::Config;
use crate::logging::Logger;

fn main() -> ExitCode {
    let config = Config::from_env();
    let logger = Logger::new(&config.log_tag);

    match run(&config, &logger) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            logger.warn(format_args!("uart-keyboard-watchdog exiting: {error}"));
            ExitCode::FAILURE
        }
    }
}
