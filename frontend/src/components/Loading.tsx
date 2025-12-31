const Loading = ({ height }: { height?: string }) => {
  return (
    <div
      className={`flex items-center justify-center ${height ? height : 'min-h-screen'}`}
    >
      <span className="loading loading-bars loading-xs"></span>
    </div>
  )
}

export default Loading
