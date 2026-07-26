/** Login-page background chosen in the admin Customize tab, shared by the app
 *  and (server-side) admin sign-in pages. `default` keeps the theme colour. */

export type LoginBgType = 'default' | 'color' | 'image'

export interface LoginAppearance {
  type: LoginBgType
  color: string
  image: string
}

const HEX = /^#[0-9a-fA-F]{6}$/

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
  if (appearance.type === 'image' && appearance.image.startsWith('data:image/')) {
    return `${fallback} url("${appearance.image}") center / cover no-repeat`
  }
  return fallback
}
