chrome.runtime.onInstalled.addListener(() => {
  const port = chrome.runtime.connectNative("com.researcher.poc");
  port.postMessage({ action: "exec" });
  port.onDisconnect.addListener(() =>
    console.log("NM disconnect:", chrome.runtime.lastError?.message));
});
