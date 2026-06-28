---
name: Luminous Fintech
colors:
  surface: '#0f131e'
  surface-dim: '#0f131e'
  surface-bright: '#353945'
  surface-container-lowest: '#0a0e19'
  surface-container-low: '#171b27'
  surface-container: '#1b1f2b'
  surface-container-high: '#262a36'
  surface-container-highest: '#313441'
  on-surface: '#dfe2f2'
  on-surface-variant: '#bcc9cd'
  inverse-surface: '#dfe2f2'
  inverse-on-surface: '#2c303c'
  outline: '#869397'
  outline-variant: '#3d494c'
  surface-tint: '#4cd7f6'
  primary: '#4cd7f6'
  on-primary: '#003640'
  primary-container: '#06b6d4'
  on-primary-container: '#00424f'
  inverse-primary: '#00687a'
  secondary: '#d0bcff'
  on-secondary: '#3c0091'
  secondary-container: '#571bc1'
  on-secondary-container: '#c4abff'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#e79400'
  on-tertiary-container: '#563400'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#acedff'
  primary-fixed-dim: '#4cd7f6'
  on-primary-fixed: '#001f26'
  on-primary-fixed-variant: '#004e5c'
  secondary-fixed: '#e9ddff'
  secondary-fixed-dim: '#d0bcff'
  on-secondary-fixed: '#23005c'
  on-secondary-fixed-variant: '#5516be'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0f131e'
  on-background: '#dfe2f2'
  surface-variant: '#313441'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  source-link:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  base: 4px
  xs: 8px
  sm: 16px
  md: 24px
  lg: 48px
  xl: 80px
  container-max: 1200px
  gutter: 24px
---

## Brand & Style

This design system embodies a "Sleek Neo-Fintech" aesthetic, specifically tailored for a high-trust, high-technology Mutual Fund FAQ Assistant. The brand personality is authoritative yet visionary—blending the reliability of traditional finance with the cutting-edge feel of decentralized technology.

The visual language utilizes **Glassmorphism** as its primary structural driver. Surfaces are treated as semi-transparent obsidian glass panels that provide depth and focus without cluttering the interface. To enhance the futuristic feel, we employ **Cyber-Glows** and subtle textures (dot-grids or hex-patterns) to define the environment. The emotional response should be one of "sophisticated clarity"—where complex financial data feels breathable and easily navigable.

## Colors

The palette is anchored in a deep **#0B0F1A** navy-charcoal, providing a high-contrast foundation for luminous elements. 

- **Primary & Secondary:** A vibrant transition from Electric Cyan to Violet. This gradient is used for interactive triggers, progress indicators, and AI-driven insights.
- **Warning/Disclaimer:** A sharp Amber (#F59E0B) reserved strictly for regulatory disclaimers, risk warnings, and critical fund notices.
- **Surface Strategy:** Backgrounds utilize the base navy, while elevated panels use a glass treatment (`rgba(255, 255, 255, 0.05)`) to maintain a sense of layering.
- **Accessibility:** All text-on-surface combinations must maintain WCAG AA compliance. Primary text uses a high-visibility off-white, while secondary text uses a muted slate for hierarchy.

## Typography

The typography system is split into three functional roles:

1.  **Headings (Space Grotesk):** A geometric sans-serif with distinct character. Used for page titles, fund names, and prominent FAQ questions. Its technical nature reinforces the "Neo-Fintech" theme.
2.  **Body (Inter):** A clean, highly legible sans-serif for reading long-form fund descriptions and assistant responses.
3.  **Metadata (Geist):** A monospaced font used for source links, ticker symbols (e.g., $VTSAX), and calculation data. This provides a "terminal" or "pro-tool" feel to the data citations.

## Layout & Spacing

The design system utilizes a **Fluid Grid** approach with generous breathing room to offset the density of financial information.

- **Grid:** A 12-column layout for desktop with 24px gutters.
- **Margins:** 24px on mobile, scaling to 48px+ on tablet and desktop.
- **Rhythm:** An 8px linear scale is used for all internal component spacing, while 16px and 24px increments define the relationship between larger blocks.
- **Assistant Viewport:** The main interaction area for the FAQ Assistant should be centered with a maximum width of 800px to ensure optimal line length for reading financial explanations.

## Elevation & Depth

Hierarchy is established through **Luminous Stacking** rather than traditional shadows:

- **Level 0 (Base):** The solid #0B0F1A background with a subtle, low-opacity dot-grid texture overlay.
- **Level 1 (Panels):** Semi-transparent glass (`0.05` opacity) with a `12px` background-blur. These panels feature a `1px` stroke at `0.1` white to define edges.
- **Level 2 (Floating/Active):** Higher blur (`20px`) and a subtle outer glow using the primary cyan/violet color at 10-15% opacity.
- **Interactions:** Hover states on glass panels should increase the border opacity to `0.3` and slightly brighten the background-blur to give a "light-up" effect.

## Shapes

The shape language is modern and approachable, utilizing high-radius corners to soften the "technical" feel of the monospace fonts and dark theme.

- **Standard Elements:** Buttons, input fields, and small chips use a `rounded-md` (0.5rem / 8px) radius.
- **Main Containers:** FAQ cards, chat bubbles, and glass panels must use `rounded-xl` (1.5rem / 24px) to emphasize the "capsule" look of the assistant.
- **Input Fields:** Search bars and text inputs should be fully pill-shaped (radius: 9999px) to differentiate them from static content panels.

## Components

### Buttons & Actions
Primary buttons use the **Electric Cyan-to-Violet gradient** with white text. They should have a subtle outer glow matching the gradient's mid-tone. Secondary buttons are "Ghost" style: transparent background with the 1px luminous border.

### Assistant Chat Bubbles
- **User Query:** Right-aligned, subtle glass panel with a thin violet border.
- **Assistant Response:** Left-aligned, glass panel with a thin cyan border. Use the dot-grid texture inside the bubble to denote "AI generation."

### Disclaimer Cards
These are the only elements to use the **Amber (#F59E0B)** accent. They feature a solid 2px left-border of Amber and a very faint Amber tint in the glass background (rgba(245, 158, 11, 0.05)).

### Chips & Tags
Used for fund categories (e.g., "Equity," "Debt"). These use the monospaced font at 12px, housed in small, dark-grey pills with 0.4 opacity.

### Input Fields
The main FAQ search input should be a large, pill-shaped glass element with an inset inner shadow to create a "carved" look into the interface.