import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Data-fetching effects are intentional throughout this dashboard app.
      'react-hooks/set-state-in-effect': 'off',
      // Several legacy hooks declare notification helpers after async callbacks.
      'react-hooks/immutability': 'off',
      'react-refresh/only-export-components': 'off',
      'no-unused-vars': 'warn',
    },
  },
])
