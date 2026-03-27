let spinner = null;

export function setSpinner(s) {
  spinner = s;
}

export function getSpinner() {
  return spinner;
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
