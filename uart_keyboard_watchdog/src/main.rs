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
    let logger = Logger::new(config.log_tag.clone());

    match run(&config, &logger) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            logger.warn(&format!("uart-keyboard-watchdog exiting: {error}"));
            ExitCode::FAILURE
        }
    }
}
