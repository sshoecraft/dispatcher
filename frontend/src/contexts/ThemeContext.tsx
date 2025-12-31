import React, { createContext, useContext, useEffect, useState } from 'react'

type Theme = 'light' | 'dark' | 'system'

interface ThemeContextType {
  theme: Theme
  setTheme: (theme: Theme) => void
  effectiveTheme: 'light' | 'dark'
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined)

export const useTheme = () => {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

interface ThemeProviderProps {
  children: React.ReactNode
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children }) => {
  const [theme, setTheme] = useState<Theme>(() => {
    const savedTheme = localStorage.getItem('dispatcher-theme')
    return (savedTheme as Theme) || 'system'
  })

  const [effectiveTheme, setEffectiveTheme] = useState<'light' | 'dark'>(
    'light'
  )

  useEffect(() => {
    const root = document.documentElement

    let resolvedTheme: 'light' | 'dark'

    if (theme === 'system') {
      resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light'
    } else {
      resolvedTheme = theme
    }

    console.log('Theme changing:', { theme, resolvedTheme })
    setEffectiveTheme(resolvedTheme)

    // Clear all existing theme attributes/classes
    root.removeAttribute('data-theme')
    root.classList.remove('light', 'dark')

    // Apply new theme
    root.setAttribute('data-theme', resolvedTheme)
    root.classList.add(resolvedTheme)

    // Also set on body for broader compatibility
    document.body.setAttribute('data-theme', resolvedTheme)
    document.body.classList.remove('light', 'dark')
    document.body.classList.add(resolvedTheme)

    // Save to localStorage
    localStorage.setItem('dispatcher-theme', theme)

    console.log('Applied theme to DOM:', {
      htmlDataTheme: root.getAttribute('data-theme'),
      htmlClasses: root.className,
      bodyDataTheme: document.body.getAttribute('data-theme'),
      bodyClasses: document.body.className,
      localStorage: localStorage.getItem('dispatcher-theme'),
    })
  }, [theme])

  useEffect(() => {
    // Listen for system theme changes when using system theme
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')

      const handleChange = (e: MediaQueryListEvent) => {
        const resolvedTheme = e.matches ? 'dark' : 'light'
        setEffectiveTheme(resolvedTheme)
        document.documentElement.setAttribute('data-theme', resolvedTheme)
        document.documentElement.classList.remove('light', 'dark')
        document.documentElement.classList.add(resolvedTheme)
      }

      mediaQuery.addEventListener('change', handleChange)
      return () => mediaQuery.removeEventListener('change', handleChange)
    }
  }, [theme])

  const value: ThemeContextType = {
    theme,
    setTheme,
    effectiveTheme,
  }

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
