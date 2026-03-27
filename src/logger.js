let spinner = null;

export function setSpinner(s) {
  spinner = s;
}

export function getSpinner() {
  return spinner;
}

// Stop the spinner permanently (used when entering the agent loop,
// where per-line logging would conflict with spinner animation).
export function stopSpinner() {
  if (spinner) {
    spinner.stop();
    spinner = null;
  }
}

export function log(msg) {
  if (spinner && spinner.isSpinning) {
    spinner.stop();
    console.log(msg);
    spinner.start();
  } else {
    console.log(msg);
  }
}
