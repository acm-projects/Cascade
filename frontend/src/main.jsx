import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './styles/theme.css'
import './styles/test-background.css' // TEST: waterfall background. Delete this line to go back to the leaves.
import App from './App.jsx'
import AuthGate from './auth/AuthGate.jsx'
import { ProjectProvider } from './context/ProjectContext.jsx'
import { ToastProvider } from './components/ui/Toast.jsx'

// BrowserRouter (URLs) -> AuthGate (Clerk or dev sign-in) -> ToastProvider (pop-up messages)
//   -> ProjectProvider (shared project state) -> App (routes)
createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthGate>
        <ToastProvider>
          <ProjectProvider>
            <App />
          </ProjectProvider>
        </ToastProvider>
      </AuthGate>
    </BrowserRouter>
  </StrictMode>,
)
