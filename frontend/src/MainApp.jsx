import { useState, useEffect } from 'react'
import '@cloudscape-design/global-styles/index.css'
import './themes.css'
import {
  TopNavigation,
} from '@cloudscape-design/components'
import App from './App'
import CliApp from './CliApp'

function MainApp() {
  const [activeView, setActiveView] = useState('interactive')
  const [theme, setTheme] = useState(() => {
    // Load theme from localStorage or default to light
    return localStorage.getItem('theme') || 'light'
  })

  // Apply theme to document when theme changes
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    document.body.className = theme === 'dark' ? 'awsui-dark-mode' : ''
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
  }

  const utilities = [
    {
      type: 'menu-dropdown',
      text: activeView === 'interactive' ? 'Interactive Cropping' : 'Batch Processing',
      description: 'Switch between UI modes',
      iconName: 'settings',
      items: [
        {
          id: 'interactive',
          text: 'Interactive Cropping',
          description: 'User-friendly interface for single image processing',
        },
        {
          id: 'cli',
          text: 'Batch Processing',
          description: 'Advanced interface for processing multiple images',
        },
      ],
      onItemClick: ({ detail }) => setActiveView(detail.id),
    },
    {
      type: 'button',
      text: theme === 'light' ? '🌙 Dark' : '☀️ Light',
      onClick: toggleTheme,
      iconName: theme === 'light' ? 'view-horizontal' : 'view-vertical',
    },
    {
      type: 'button',
      text: 'GitHub',
      href: 'https://github.com/garystafford/image-cropper',
      external: true,
    },
  ]

  return (
    <>
      <TopNavigation
        identity={{
          href: '#',
          title: 'AI Image Cropper',
          logo: {
            src: '/crop.png',
            alt: 'AI Image Cropper',
          },
        }}
        utilities={utilities}
        i18nStrings={{
          overflowMenuTriggerText: 'More',
          overflowMenuTitleText: 'All',
        }}
      />
      <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '2rem' }}>
        {activeView === 'interactive' ? <App /> : <CliApp />}
      </div>
    </>
  )
}

export default MainApp
