import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './styles/theme.css'
import App from './App.jsx'
import AuthGate from './auth/AuthGate.jsx'
import { ProjectProvider } from './context/ProjectContext.jsx'

// BrowserRouter (URLs) -> AuthGate (Clerk or dev sign-in) -> ProjectProvider (shared project state) -> App (routes)
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthGate>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </AuthGate>
    </BrowserRouter>
  </StrictMode>,
)
