// Lets the Quit button tell the app that the server has stopped, so the app stops showing
// pages that can no longer load anything.
import { createContext, useContext } from 'react'

export const StoppedContext = createContext<() => void>(() => {})

export function useMarkStopped() {
  return useContext(StoppedContext)
}
