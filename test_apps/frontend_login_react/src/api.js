import { fetch } from './fetch';
import { BusinessLogicInterface } from './businessLogic';

const login = async (username, password, businessLogic) => {
  try {
    const response = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json();
    return businessLogic.processLoginResponse(data);
  } catch (err) {
    if (err.message.includes('Error code:')) {
      const errorCode = err.message.split('Error code: ')[1].split(', Error message: ')[0];
      const errorMessage = err.message.split(', Error message: ')[1];
      throw new Error(`Error code: ${errorCode}, Error message: ${errorMessage}`);
    } else {
      throw new Error(`Error code: ${err.code}, Error message: ${err.message}`);
    }
  }
};

export { login };