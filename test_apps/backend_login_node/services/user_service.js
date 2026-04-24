const auth = require('../controller/auth');
const userRepository = require('../repository/user_repository');
const ErrorCode = require('../controller/auth').ErrorCode;

class UserService {
    constructor(userRepository) {
        this.auth = auth(userRepository);
        this.userRepository = userRepository;
    }

    async login(username, password) {
        try {
            return await this.auth.authenticate({ username, password });
        } catch (err) {
            throw { status: err.status, message: err.message, error_code: err.error_code };
        }
    }

    async createUser(username, password) {
        try {
            return await this.userRepository.createUser(username, password);
        } catch (err) {
            throw { status: err.status, message: err.message, error_code: err.error_code };
        }
    }
}

module.exports = new UserService(require('../repository/user_repository'));