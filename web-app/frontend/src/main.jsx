import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import { ensureSiteSession } from './api/siteSession'

function render() {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  )
}

// Get the site token cookie before the first API call goes out (components
// fire requests on mount). Never block the page for long if the API is slow —
// the client retries the bootstrap on its own.
const bootstrapTimeout = new Promise((resolve) => setTimeout(resolve, 3000))
Promise.race([ensureSiteSession().catch(() => {}), bootstrapTimeout]).then(render)
