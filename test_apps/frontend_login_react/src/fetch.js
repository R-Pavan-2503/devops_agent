import { fetch as originalFetch } from 'node-fetch';

const fetch = async (url, options) => {
  try {
    const response = await originalFetch(url, options);
    if (!response.ok) {
      const error = new Error(response.statusText);
      error.code = response.status;
      throw error;
    }
    return response;
  } catch (err) {
    throw new Error(`Error code: ${err.code}, Error message: ${err.message}`);
  }
};

export { fetch };