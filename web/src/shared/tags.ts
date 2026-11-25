// Tags typed as one line: "Z2, cobbles , base" → ["Z2", "cobbles", "base"]. The server
// lower-cases them and checks their length; commas can't be inside a tag.
export function parseTags(text: string): string[] {
  const seen = new Set<string>()
  return text
    .split(',')
    .map((tag) => tag.trim())
    .filter((tag) => {
      const key = tag.toLowerCase()
      if (!tag || seen.has(key)) return false
      seen.add(key)
      return true
    })
}
