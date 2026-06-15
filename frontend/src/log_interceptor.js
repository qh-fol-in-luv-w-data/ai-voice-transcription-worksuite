window.onerror = function(message, source, lineno, colno, error) {
  document.body.innerHTML += `<div style="position:fixed; top:0; left:0; right:0; background:red; color:white; z-index:9999; padding:20px; font-family:monospace;"><h3>GLOBAL ERROR</h3><p>${message}</p><p>${source}:${lineno}:${colno}</p><pre>${error && error.stack}</pre></div>`;
};
window.addEventListener('unhandledrejection', function(event) {
  document.body.innerHTML += `<div style="position:fixed; top:0; left:0; right:0; background:red; color:white; z-index:9999; padding:20px; font-family:monospace;"><h3>UNHANDLED REJECTION</h3><p>${event.reason}</p><pre>${event.reason && event.reason.stack}</pre></div>`;
});
