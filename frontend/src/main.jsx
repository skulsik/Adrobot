import React from 'react'
import ReactDOM from 'react-dom/client'

function App() {
  return (
    <main style={{
      minHeight: '100vh',
      display: 'grid',
      placeItems: 'center',
      background: '#111827',
      color: '#f9fafb',
      fontFamily: 'Arial, sans-serif',
    }}>
      <div style={{ textAlign: 'center' }}>
        <h1>Adrobot</h1>
        <p>Управление рекламными кампаниями</p>
        <span>Application is running</span>
      </div>
    </main>
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)