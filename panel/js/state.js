const TOKEN_KEY = "dispwatter_token";
const DEVICE_KEY = "dispwatter_device";

export const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  user: null,
  devices: [],
  selectedId: localStorage.getItem(DEVICE_KEY) || "",
  connected: false,
  wifi: [],
  audit: [],
};

export function setToken(token) {
  state.token = token || "";
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function setSelectedDevice(deviceId) {
  state.selectedId = deviceId || "";
  if (deviceId) {
    localStorage.setItem(DEVICE_KEY, deviceId);
  } else {
    localStorage.removeItem(DEVICE_KEY);
  }
}

export function selectedDevice() {
  return state.devices.find((dev) => dev.id === state.selectedId) || null;
}

export function upsertDevice(device) {
  const index = state.devices.findIndex((item) => item.id === device.id);
  if (index >= 0) {
    state.devices[index] = { ...state.devices[index], ...device };
  } else {
    state.devices.push(device);
  }
}
