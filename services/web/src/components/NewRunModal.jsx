import { useNewRunModal } from '../NewRunModalContext.jsx'
import Modal from './Modal.jsx'
import NewRunForm from './NewRunForm.jsx'

export default function NewRunModal() {
  const { request, close } = useNewRunModal()

  if (!request) return null

  return (
    <Modal onClose={close} className="modal-panel-form">
      <NewRunForm initialWorkflow={request.workflow} initialStartFrom={request.startFrom} onDone={close} />
    </Modal>
  )
}
