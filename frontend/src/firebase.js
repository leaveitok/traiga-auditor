/**
 * firebase.js — Firebase app initialisation.
 *
 * Requires a .env file (copy .env.example) with:
 *   VITE_FIREBASE_API_KEY
 *   VITE_FIREBASE_AUTH_DOMAIN
 *   VITE_FIREBASE_PROJECT_ID
 *
 * After adding .env, restart the Vite dev server.
 */
import { initializeApp }     from 'firebase/app'
import { getAuth, GoogleAuthProvider } from 'firebase/auth'

const firebaseConfig = {
  apiKey:    import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId:  import.meta.env.VITE_FIREBASE_PROJECT_ID,
}

export const firebaseApp      = initializeApp(firebaseConfig)
export const firebaseAuth     = getAuth(firebaseApp)
export const googleProvider   = new GoogleAuthProvider()

// Request email scope so we always get the user's email back
googleProvider.addScope('email')
