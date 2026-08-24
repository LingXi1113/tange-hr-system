export async function prepareApplication() {
  if (__PROJECT_TYPE__ !== 'embedded') {
    return undefined;
  }

  const { prepareEmbeddedSso } = await import('./embeddedSso');
  return prepareEmbeddedSso({ appId: __APP_ID__ });
}
