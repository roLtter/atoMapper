package jobs

import (
	"context"
	"fmt"
	"strings"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type objectStore struct {
	client *minio.Client
	bucket string
}

func newObjectStore(cfg Config) (*objectStore, error) {
	if cfg.MinioEndpoint == "" {
		return nil, nil
	}
	client, err := minio.New(cfg.MinioEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinioAccessKey, cfg.MinioSecretKey, ""),
		Secure: cfg.MinioSecure,
	})
	if err != nil {
		return nil, err
	}
	ctx := context.Background()
	exists, err := client.BucketExists(ctx, cfg.MinioBucket)
	if err != nil {
		return nil, err
	}
	if !exists {
		if err := client.MakeBucket(ctx, cfg.MinioBucket, minio.MakeBucketOptions{}); err != nil {
			return nil, err
		}
	}
	return &objectStore{client: client, bucket: cfg.MinioBucket}, nil
}

func (o *objectStore) putFile(jobID, name, path string) error {
	if o == nil {
		return nil
	}
	_, err := o.client.FPutObject(
		context.Background(),
		o.bucket,
		fmt.Sprintf("%s/%s", jobID, name),
		path,
		minio.PutObjectOptions{ContentType: contentType(name)},
	)
	return err
}

func contentType(name string) string {
	if strings.HasSuffix(name, ".json") {
		return "application/json"
	}
	if strings.HasSuffix(name, ".md") {
		return "text/markdown"
	}
	return "text/plain"
}

func (o *objectStore) enabled() bool {
	return o != nil && o.client != nil
}
