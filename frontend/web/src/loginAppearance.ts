/** Login-page background chosen in the admin Customize tab, shared by the app
 *  and (server-side) admin sign-in pages. `default` keeps the theme colour. */

export type LoginBgType = 'default' | 'color' | 'image'

export interface LoginAppearance {
  type: LoginBgType
  color: string
  image: string
  /** Release label shown on the sign-in panels (from the top-level VERSION file). */
  version?: string
}

const HEX = /^#[0-9a-fA-F]{6}$/
// Mirrors the server-side validation: a strict image data URI whose payload is
// pure base64 (no ", ), <, whitespace …). Validating here too means a tampered
// or MITM-injected appearance response can never inject extra CSS / an external
// url() layer, regardless of what the fetch returned.
const DATA_IMAGE = /^data:image\/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/]+={0,2}$/

/**
 * CSS `background` value for the sign-in backdrop. Falls back to the theme
 * colour for `default`, invalid input, or a null appearance. Values are also
 * validated server-side; the guards here are defence-in-depth so a bad stored
 * value can never inject CSS.
 */
export function loginBackground(
  appearance: LoginAppearance | null | undefined,
  fallback = 'var(--bg-grouped)',
): string {
  if (!appearance) return fallback
  if (appearance.type === 'color' && HEX.test(appearance.color)) {
    return appearance.color
  }
  if (appearance.type === 'image' && DATA_IMAGE.test(appearance.image)) {
    return `${fallback} url("${appearance.image}") center / cover no-repeat`
  }
  return fallback
}
