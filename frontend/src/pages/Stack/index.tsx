import { useState } from 'react'

import reactLogo from '@/assets/react.svg'
import viteLogo from '/vite.svg'
import axiosLogo from '@/assets/axios.svg'
import reactRouterLogo from '@/assets/react-router.svg'
import tailwindcssLogo from '@/assets/tailwindcss.svg'
import daisyuiLogo from '@/assets/daisyui.svg'
import meta from '@/../package.json'

import './stack.css'

interface Tool {
  name: string
  href: string
  version: string
  logo?: string
}

const stack: Tool[] = [
  {
    name: 'vite',
    href: 'https://vite.dev',
    version: meta.devDependencies['vite'],
    logo: viteLogo,
  },
  {
    name: 'react',
    href: 'https://react.dev',
    version: meta.dependencies['react'],
    logo: reactLogo,
  },
  {
    name: 'axios',
    href: 'https://axios-http.com/',
    version: meta.dependencies['axios'],
    logo: axiosLogo,
  },
  {
    name: 'react-router',
    href: 'https://reactrouter.com/',
    version: meta.dependencies['react-router'],
    logo: reactRouterLogo,
  },
  {
    name: 'tailwindcss',
    href: 'https://tailwindcss.com/',
    version: meta.dependencies['tailwindcss'],
    logo: tailwindcssLogo,
  },
  {
    name: 'daisyui',
    href: 'https://daisyui.com/',
    version: meta.dependencies['daisyui'],
    logo: daisyuiLogo,
  },
]

function Stack() {
  const [message, setMessage] = useState('Welcome to Dispatcher!')

  const mouseHoverHandler = (tool: Tool) => {
    setMessage(`${tool.name} v${tool.version.substring(1)}`)
  }

  return (
    <main
      id="stack-page"
      className="flex place-items-center justify-center min-h-screen w-full"
    >
      <section className="mx-0 my-auto p-8 text-center">
        <h1>{message}</h1>
        <div className="divider mb-10">stack</div>
        <div className="flex">
          {stack.map((tool) => (
            <a
              href={tool.href}
              target="_blank"
              onMouseOver={() => mouseHoverHandler(tool)}
            >
              <div className="avatar indicator">
                <span className="indicator-item indicator-center badge badge-secondary">
                  {tool.name}
                  {tool.version}
                </span>
                <img
                  src={tool.logo}
                  className={`logo ${tool.name}`}
                  alt={`${tool.name} logo`}
                />
              </div>
            </a>
          ))}
        </div>
      </section>
    </main>
  )
}

export default Stack
