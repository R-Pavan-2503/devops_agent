const bcrypt = require('bcrypt');
const ErrorCode = {
    NO_ERROR: 'NO_ERROR',
    INVALID_CREDENTIALS: 'INVALID_CREDENTIALS',
    INVALID_REQUEST: 'INVALID_REQUEST',
    PASSWORD_TOO_SHORT: 'PASSWORD_TOO_SHORT'
};

class Auth {
    constructor(userRepository) {
        this.userRepository = userRepository;
    }

    async authenticate({ username, password }) {
        if (!username || !password) {
            throw { status: 400, message: "username and password are required", error_code: ErrorCode.INVALID_REQUEST };
        }

        const user = await this.userRepository.getUser(username);
        if (!user) {
            throw { status: 401, message: "unauthorized", error_code: ErrorCode.INVALID_CREDENTIALS };
        }

        const isValidPassword = await bcrypt.compare(password, user.password);
        if (!isValidPassword) {
            throw { status: 401, message: "unauthorized", error_code: ErrorCode.INVALID_CREDENTIALS };
        }

        return { 
            id: user.id, 
            username: user.username, 
            status: "active", 
            created_at: user.created_at,
            error_code: ErrorCode.NO_ERROR,
            contract: "login",
            format: "json",
            status_code: 200
        };
    }
}

module.exports = (userRepository) => new Auth(userRepository);
module.exports.ErrorCode = ErrorCode;