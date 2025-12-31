import { toast, Bounce, ToastOptions } from 'react-toastify'

const defaultOptions: ToastOptions = {
  position: 'bottom-right',
  autoClose: false,
  hideProgressBar: false,
  closeOnClick: false,
  pauseOnHover: true,
  draggable: true,
  progress: undefined,
  theme: 'light',
  transition: Bounce,
}

export const showErrorToast = (
  message = 'Something went wrong, please try again later!',
  options: ToastOptions = {}
) => toast.error(message, { ...defaultOptions, ...options })
