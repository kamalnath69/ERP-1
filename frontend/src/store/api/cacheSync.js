const CHANNEL_NAME = "edvatiq-cache-v1";
let channel;

function getChannel() {
  if (channel !== undefined) return channel;
  channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(CHANNEL_NAME);
  return channel;
}

export function broadcastInvalidation(resources) {
  if (!resources?.length) return;
  getChannel()?.postMessage({ type: "invalidate", resources: [...new Set(resources)] });
}

export function setupCacheSync(dispatch, api) {
  const activeChannel = getChannel();
  if (!activeChannel) return () => {};
  activeChannel.onmessage = (event) => {
    if (event.data?.type !== "invalidate" || !Array.isArray(event.data.resources)) return;
    dispatch(api.util.invalidateTags(event.data.resources.map((id) => ({ type: "Resource", id }))));
  };
  return () => { activeChannel.onmessage = null; };
}
