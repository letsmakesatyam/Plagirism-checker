import client from "./client";

export const listInternetSources = () => client.get("/internet-sources").then((r) => r.data);
export const addInternetSourceFromText = (payload) =>
  client.post("/internet-sources", payload).then((r) => r.data);
export const addInternetSourceFromUrl = (payload) =>
  client.post("/internet-sources/from-url", payload).then((r) => r.data);
