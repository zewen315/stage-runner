import { createContext, useContext, useState } from 'react'

const NewRunModalContext = createContext(null)

export function NewRunModalProvider({ children }) {
  const [request, setRequest] = useState(null) // null = closed, {workflow, startFrom} = open

  const open = (initial = {}) => setRequest({ workflow: initial.workflow || '', startFrom: initial.startFrom || '' })
  const close = () => setRequest(null)

  return (
    <NewRunModalContext.Provider value={{ request, open, close }}>{children}</NewRunModalContext.Provider>
  )
}

export function useNewRunModal() {
  return useContext(NewRunModalContext)
}
