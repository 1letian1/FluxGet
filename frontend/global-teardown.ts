export default async function globalTeardown() {
  await fetch('http://127.0.0.1:8766/test-shutdown').catch(() => undefined)
}
