/** 스캐폴딩 단계 스텁 표식. 구현 시 제거된다. */
export class NotImplementedError extends Error {
  constructor(feature: string) {
    super(`Not implemented: ${feature}`);
    this.name = "NotImplementedError";
  }
}

/** 입력이 유효하지 않을 때 (서비스 경계에서 던짐) */
export class ValidationError extends Error {
  constructor(
    message: string,
    public readonly warnings: string[] = [],
  ) {
    super(message);
    this.name = "ValidationError";
  }
}

/** 대상 리소스가 없거나 접근 불가할 때 (라우트에서 404로 매핑) */
export class NotFoundError extends Error {
  constructor(resource: string) {
    super(`Not found: ${resource}`);
    this.name = "NotFoundError";
  }
}
