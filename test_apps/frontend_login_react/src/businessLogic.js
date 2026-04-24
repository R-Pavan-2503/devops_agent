const processLoginResponse = (data) => {
  if (data.status === 'success') {
    return {
      id: data.id,
      status: data.status,
      created_at: data.created_at,
      username: data.username,
    };
  } else {
    return {
      error_code: data.error_code,
      error_message: data.error_message,
    };
  }
};

export const businessLogic = {
  processLoginResponse,
};