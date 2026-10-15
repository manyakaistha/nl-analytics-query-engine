
        module.exports = {
            content: ['./static/index.html', './static/app.js'],
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'system-ui', 'sans-serif'],
                        serif: ['"Instrument Serif"', 'serif'],
                        mono: ['JetBrains Mono', 'monospace'],
                    },
                    colors: {
                        // Warm brown neutrals
                        ink: {
                            50: '#faf6f0', 100: '#f3ebdf', 200: '#e7dac7', 300: '#cdb89c', 400: '#a88e70',
                            500: '#86694d', 600: '#6b4f37', 700: '#543c29', 800: '#3f2c1e', 900: '#2b1d13',
                        },
                        accent: {
                            400: '#a8703f',
                            500: '#8b5a2b',
                            600: '#74461f',
                            700: '#5c3616',
                        },
                    },
                    animation: {
                        'fade-in': 'fadeIn 0.4s ease-out',
                        'slide-up': 'slideUp 0.4s ease-out',
                        'pulse-dot': 'pulseDot 1.4s infinite ease-in-out both',
                    },
                    keyframes: {
                        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
                        slideUp: { '0%': { opacity: '0', transform: 'translateY(16px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
                        pulseDot: { '0%, 80%, 100%': { transform: 'scale(0)' }, '40%': { transform: 'scale(1)' } },
                    },
                },
            },
        }
    