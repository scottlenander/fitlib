// Apply a remembered theme before the first paint, so dark mode never flashes light.
// A plain file rather than an inline script, which the Content-Security-Policy blocks.
try {
  const theme = localStorage.getItem('fitlib.theme')
  if (theme === 'light' || theme === 'dark') document.documentElement.dataset.theme = theme
} catch {}
