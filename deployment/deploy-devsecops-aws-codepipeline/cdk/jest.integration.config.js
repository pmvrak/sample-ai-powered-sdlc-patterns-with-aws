module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/test/**/*.integration.test.ts'],
  transform: {
    '^.+\\.tsx?$': ['ts-jest', {tsconfig: './tsconfig.json'}]
  },
  moduleFileExtensions: ['ts', 'tsx', 'js', 'jsx', 'json', 'node'],
  verbose: true,
    testTimeout: 30000,
    globals: {
        'ts-jest': {
            tsconfig: {
                "target": "ES2018",
                "module": "commonjs",
                "strict": true,
                "esModuleInterop": true,
                "skipLibCheck": true,
                "forceConsistentCasingInFileNames": true,
                "strictNullChecks": true,
                "noUncheckedIndexedAccess": true
            }
        }
    }
};
