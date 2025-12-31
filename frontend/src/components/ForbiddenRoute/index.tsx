import { useNavigate } from 'react-router'

const ForbiddenRoute = () => {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col h-screen items-center justify-center">
      <h1 className="text-4xl font-bold">403 Forbidden</h1>
      <p className="mt-4 text-lg">
        You do not have permission to access this page.
      </p>
      <button
        className="mt-8 px-6 py-2 bg-[#007DC5] text-white rounded hover:bg-[#005fa3] transition"
        onClick={() => navigate('/dashboard')}
      >
        Go to Dashboard
      </button>
    </div>
  )
}

export default ForbiddenRoute
