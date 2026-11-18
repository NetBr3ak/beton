use std::env;
use std::process::{Command, ExitCode};

fn main() -> ExitCode {
    let python = env::var_os("BETON_PYTHON")
        .unwrap_or_else(|| if cfg!(windows) { "python" } else { "python3" }.into());
    let result = Command::new(&python)
        .args(["-I", "-c", include_str!("../../packaging/bootstrap.py")])
        .arg(include_str!("../beton_checks/discovery.py"))
        .arg(include_str!("../beton_checks/__main__.py"))
        .args(env::args_os().skip(1))
        .status();
    match result {
        Ok(status) => match status.code() {
            Some(code) => ExitCode::from(u8::try_from(code).unwrap_or(1)),
            None => ExitCode::FAILURE,
        },
        Err(error) => {
            eprintln!(
                "beton: cannot start {}: {error}. Install Python 3.11+ or set BETON_PYTHON.",
                python.to_string_lossy()
            );
            ExitCode::FAILURE
        }
    }
}
