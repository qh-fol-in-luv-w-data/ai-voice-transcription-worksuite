function appendDebugError(title, lines) {
  const panel = document.createElement('div')
  panel.style.cssText = 'position:fixed;top:0;left:0;right:0;background:red;color:white;z-index:9999;padding:20px;font-family:monospace;white-space:pre-wrap;'

  const heading = document.createElement('h3')
  heading.textContent = title
  panel.appendChild(heading)

  for (const line of lines) {
    const block = document.createElement('pre')
    block.textContent = String(line || '')
    panel.appendChild(block)
  }

  document.body.appendChild(panel)
}

if (import.meta.env.DEV) {
  window.onerror = function(message, source, lineno, colno, error) {
    appendDebugError('GLOBAL ERROR', [message, `${source}:${lineno}:${colno}`, error?.stack])
  }

  window.addEventListener('unhandledrejection', function(event) {
    appendDebugError('UNHANDLED REJECTION', [event.reason, event.reason?.stack])
  })
}
