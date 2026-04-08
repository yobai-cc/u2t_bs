(() => {
  const logBox = document.getElementById("runtime-stream");
  if (!logBox) {
    return;
  }

  let socket;

  const connect = () => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/ws/runtime`);

    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      const text = JSON.stringify(payload, null, 2);
      logBox.textContent = `${new Date().toLocaleString()}\n${text}\n\n${logBox.textContent}`;
    };

    socket.onclose = () => {
      window.setTimeout(connect, 1500);
    };
  };

  connect();
})();
